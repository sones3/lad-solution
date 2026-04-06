from __future__ import annotations

from collections.abc import Iterator
import json
from threading import Lock

import cv2
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.models.lot_models import (
    LotAnalysisResponseModel,
    LotCsvRowModel,
    LotDocumentModel,
    LotFolderModel,
    LotFolderProcessRequestModel,
    LotIssueModel,
    LotSummaryModel,
)
from app.models.template_models import TemplateModel
from app.services.lot_csv import parse_lot_csv
from app.services.lot_folder_workflow import process_lot_workspace
from app.services.lot_matcher import (
    LotDocumentSeed,
    build_lot_match_results,
    evaluate_lot_document,
)
from app.services.lot_separator import (
    LotSeparatorConfig,
    LotSeparationPageModel,
    iter_lot_pdf_pages,
    iter_lot_pdf_pages_with_paper,
)
from app.services.template_feature_store import load_paper_template_features
from app.services.lot_workspace import get_lot_workspace, list_lot_workspaces
from app.storage.template_store import TemplateStore

router = APIRouter(prefix="/lots", tags=["lots"])
PROCESS_LOCK = Lock()


def get_store() -> TemplateStore:
    from app.main import store

    return store


def _read_pdf_upload(file: UploadFile) -> bytes:
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400, detail="Only PDF files are supported for lots"
        )

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
    return raw


def _read_csv_upload(file: UploadFile) -> bytes:
    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    return raw


def _parse_separator_config(
    *,
    separation_method: str,
    template_id: str | None,
    paper_threshold: float,
    dpi: int,
    binarizer: str,
    lang: str,
    psm: int,
    oem: int,
    timeout: int,
    min_keywords: int,
    workers: int,
) -> LotSeparatorConfig:
    normalized_method = separation_method.strip().lower()
    if normalized_method not in {"ocr", "paper"}:
        raise HTTPException(
            status_code=400, detail="separationMethod must be 'ocr' or 'paper'"
        )
    if min_keywords < 1 or min_keywords > 4:
        raise HTTPException(
            status_code=400, detail="minKeywords must be between 1 and 4"
        )
    if dpi <= 0 or timeout <= 0 or workers <= 0:
        raise HTTPException(
            status_code=400, detail="dpi, timeout, and workers must be positive"
        )
    if paper_threshold < 0.0 or paper_threshold > 1.0:
        raise HTTPException(
            status_code=400, detail="paperThreshold must be between 0 and 1"
        )

    if normalized_method == "paper" and not template_id:
        raise HTTPException(
            status_code=400,
            detail="templateId is required when separationMethod is 'paper'",
        )

    return LotSeparatorConfig(
        separation_method=normalized_method,
        template_id=template_id,
        paper_threshold=paper_threshold,
        dpi=dpi,
        binarizer="otsu",
        lang="fra",
        psm=psm,
        oem=oem,
        timeout=timeout,
        min_keywords=min_keywords,
        workers=workers,
    )


def _load_template_image(
    template: TemplateModel, template_store: TemplateStore
) -> cv2.typing.MatLike:
    image_path = template_store.data_dir.parent / template.imagePath.removeprefix("/")
    image = cv2.imread(str(image_path))
    if image is None:
        raise HTTPException(
            status_code=500, detail="Template image file does not exist"
        )
    return image


def _build_lot_analysis(
    pdf_raw: bytes,
    csv_raw: bytes,
    *,
    config: LotSeparatorConfig,
    template_store: TemplateStore,
) -> Iterator[dict[str, object]]:
    try:
        csv_rows = parse_lot_csv(csv_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    yield {
        "type": "started",
        "csvRowCount": len(csv_rows),
        "config": {
            "separationMethod": config.separation_method,
            "templateId": config.template_id,
            "paperThreshold": config.paper_threshold,
            "dpi": config.dpi,
            "binarizer": config.binarizer,
            "lang": config.lang,
            "psm": config.psm,
            "oem": config.oem,
            "timeout": config.timeout,
            "minKeywords": config.min_keywords,
            "workers": config.workers,
        },
    }

    pages: list[LotSeparationPageModel] = []
    issues: list[LotIssueModel] = []
    provisional_documents: list[LotDocumentModel] = []

    page_iterator: Iterator[LotSeparationPageModel]
    if config.separation_method == "paper":
        template = template_store.get_template(config.template_id or "")
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")
        if template.paperFeatureArtifact is None:
            raise HTTPException(
                status_code=400,
                detail="Selected template does not have a paper artifact yet",
            )
        artifact_path = (
            template_store.data_dir.parent
            / template.paperFeatureArtifact.artifactPath.removeprefix("/")
        )
        if not artifact_path.exists():
            raise HTTPException(
                status_code=500, detail="Paper template artifact file does not exist"
            )
        try:
            template_features = load_paper_template_features(artifact_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=500, detail="Failed to load paper template artifact"
            ) from exc
        template_image = _load_template_image(template, template_store)
        page_iterator = iter_lot_pdf_pages_with_paper(
            pdf_raw,
            config=config,
            template=template,
            template_image=template_image,
            template_features=template_features,
        )
    else:
        page_iterator = iter_lot_pdf_pages(pdf_raw, config=config)

    try:
        for page in page_iterator:
            pages.append(page)
            yield {"type": "page", "page": page.model_dump(mode="json")}

            if not page.isNewDocument:
                continue

            document_seed = LotDocumentSeed(
                index=page.pageNumber,
                start_page=page.pageNumber,
                end_page=page.pageNumber,
                page_count=1,
                first_page=page,
            )
            document, document_issues, claimed_row = evaluate_lot_document(
                document=document_seed, csv_rows=csv_rows
            )
            provisional_documents.append(document)
            issues.extend(document_issues)
            yield {"type": "document", "document": document.model_dump(mode="json")}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pages.sort(key=lambda page: page.pageNumber)
    start_pages = sorted(page.pageNumber for page in pages if page.isNewDocument)

    if not start_pages:
        issues.append(
            LotIssueModel(
                code="no_start_pages", message="No document start pages were detected"
            )
        )
    elif start_pages[0] != 1:
        issues.append(
            LotIssueModel(
                code="leading_pages_before_first_start",
                message=f"First detected document starts at page {start_pages[0]}, not page 1",
                pageNumber=start_pages[0],
            )
        )
    issues.extend(
        _build_long_gap_warnings(start_pages=start_pages, total_pages=len(pages))
    )

    page_map = {page.pageNumber: page for page in pages}
    final_document_seeds = [
        LotDocumentSeed(
            index=index,
            start_page=start_page,
            end_page=(start_pages[index] - 1)
            if index < len(start_pages)
            else len(pages),
            page_count=((start_pages[index] - 1) - start_page + 1)
            if index < len(start_pages)
            else (len(pages) - start_page + 1),
            first_page=page_map.get(start_page),
        )
        for index, start_page in enumerate(start_pages, start=1)
    ]

    documents, match_issues, validation_blocked = build_lot_match_results(
        documents=final_document_seeds,
        csv_rows=csv_rows,
    )
    issues.extend(match_issues)

    for document in documents:
        yield {"type": "document", "document": document.model_dump(mode="json")}

    summary = LotSummaryModel(
        totalPages=len(pages),
        csvRowCount=len(csv_rows),
        detectedDocumentCount=len(documents),
        matchedDocumentCount=sum(
            1 for document in documents if document.assignedRow is not None
        ),
        validationBlocked=validation_blocked
        or any(issue.severity != "warning" for issue in issues),
    )

    response = LotAnalysisResponseModel(
        summary=summary,
        csvRows=[
            LotCsvRowModel(
                rowNumber=row.row_number,
                commande=row.commande,
                clientNumber=row.client_number,
                distributeur=row.distributeur,
                client=row.client,
                statut=row.statut,
                cote=row.cote,
                caisse=row.caisse,
            )
            for row in csv_rows
        ],
        pages=pages,
        startPages=start_pages,
        documents=documents,
        issues=issues,
    )
    yield {"type": "complete", "result": response.model_dump(mode="json")}


def _build_long_gap_warnings(
    *, start_pages: list[int], total_pages: int
) -> list[LotIssueModel]:
    warnings: list[LotIssueModel] = []
    if total_pages <= 0:
        return warnings

    previous_start = None
    for start_page in [*start_pages, total_pages + 1]:
        if previous_start is None:
            gap_start = 1
            gap_end = start_page - 1
        else:
            gap_start = previous_start + 1
            gap_end = start_page - 1

        gap_length = gap_end - gap_start + 1
        if gap_length >= 15:
            warnings.append(
                LotIssueModel(
                    code="long_gap_without_start",
                    severity="warning",
                    message=f"{gap_length} pages without a new document between pages {gap_start} and {gap_end}",
                    pageNumber=gap_start,
                )
            )
        previous_start = start_page if start_page <= total_pages else previous_start

    return warnings


@router.post("/analyze", response_model=LotAnalysisResponseModel)
def analyze_lot(
    pdf: UploadFile = File(...),
    csv: UploadFile = File(...),
    separationMethod: str = Form(default="ocr"),
    templateId: str | None = Form(default=None),
    paperThreshold: float = Form(default=0.35),
    dpi: int = Form(default=150),
    binarizer: str = Form(default="otsu"),
    lang: str = Form(default="fra"),
    psm: int = Form(default=6),
    oem: int = Form(default=1),
    timeout: int = Form(default=12),
    minKeywords: int = Form(default=3),
    workers: int = Form(default=6),
    template_store: TemplateStore = Depends(get_store),
) -> LotAnalysisResponseModel:
    config = _parse_separator_config(
        separation_method=separationMethod,
        template_id=templateId,
        paper_threshold=paperThreshold,
        dpi=dpi,
        binarizer=binarizer,
        lang=lang,
        psm=psm,
        oem=oem,
        timeout=timeout,
        min_keywords=minKeywords,
        workers=workers,
    )

    events = _build_lot_analysis(
        _read_pdf_upload(pdf),
        _read_csv_upload(csv),
        config=config,
        template_store=template_store,
    )
    for event in events:
        if event["type"] == "complete":
            return LotAnalysisResponseModel.model_validate(event["result"])
    raise HTTPException(status_code=500, detail="Lot analysis did not complete")


@router.post("/analyze/stream")
def analyze_lot_stream(
    pdf: UploadFile = File(...),
    csv: UploadFile = File(...),
    separationMethod: str = Form(default="ocr"),
    templateId: str | None = Form(default=None),
    paperThreshold: float = Form(default=0.35),
    dpi: int = Form(default=150),
    binarizer: str = Form(default="otsu"),
    lang: str = Form(default="fra"),
    psm: int = Form(default=6),
    oem: int = Form(default=1),
    timeout: int = Form(default=12),
    minKeywords: int = Form(default=3),
    workers: int = Form(default=6),
    template_store: TemplateStore = Depends(get_store),
) -> StreamingResponse:
    config = _parse_separator_config(
        separation_method=separationMethod,
        template_id=templateId,
        paper_threshold=paperThreshold,
        dpi=dpi,
        binarizer=binarizer,
        lang=lang,
        psm=psm,
        oem=oem,
        timeout=timeout,
        min_keywords=minKeywords,
        workers=workers,
    )
    pdf_raw = _read_pdf_upload(pdf)
    csv_raw = _read_csv_upload(csv)

    def stream() -> Iterator[bytes]:
        try:
            for event in _build_lot_analysis(
                pdf_raw, csv_raw, config=config, template_store=template_store
            ):
                yield (json.dumps(event) + "\n").encode("utf-8")
        except HTTPException as exc:
            yield (
                json.dumps({"type": "error", "error": str(exc.detail)}) + "\n"
            ).encode("utf-8")

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/folders", response_model=list[LotFolderModel])
def list_lot_folders() -> list[LotFolderModel]:
    return [
        LotFolderModel(
            name=workspace.name,
            lotNumber=workspace.lot_number,
            status=workspace.status,
            pdfPresent=workspace.pdf_present,
            csvPresent=workspace.csv_present,
            sepPresent=workspace.sep_present,
            workbookPresent=workspace.workbook_present,
            lastModified=_format_timestamp(workspace.last_modified),
            errors=workspace.errors,
            config={
                "templateId": workspace.config.template_id,
                "paperThreshold": workspace.config.paper_threshold,
            },
        )
        for workspace in list_lot_workspaces()
    ]


@router.post("/folders/{lot_name}/process/stream")
def process_lot_folder_stream(
    lot_name: str,
    payload: LotFolderProcessRequestModel = Body(...),
    template_store: TemplateStore = Depends(get_store),
) -> StreamingResponse:
    workspace = get_lot_workspace(lot_name)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Lot not found")
    if workspace.status != "ready":
        raise HTTPException(
            status_code=400, detail="Lot is incomplete and cannot be processed"
        )
    if workspace.outputs_exist and not payload.confirmRegenerate:
        raise HTTPException(
            status_code=409,
            detail="Lot already has generated outputs and requires confirmation",
        )
    if not (0.0 <= payload.paperThreshold <= 1.0):
        raise HTTPException(
            status_code=400, detail="paperThreshold must be between 0 and 1"
        )
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(
            status_code=409, detail="Another lot is already being processed"
        )

    def stream() -> Iterator[bytes]:
        try:
            for event in process_lot_workspace(
                workspace=workspace,
                template_id=payload.templateId,
                paper_threshold=payload.paperThreshold,
                template_store=template_store,
            ):
                yield (json.dumps(event) + "\n").encode("utf-8")
        except ValueError as exc:
            yield (json.dumps({"type": "error", "error": str(exc)}) + "\n").encode(
                "utf-8"
            )
        except Exception as exc:
            yield (json.dumps({"type": "error", "error": str(exc)}) + "\n").encode(
                "utf-8"
            )
        finally:
            PROCESS_LOCK.release()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def _format_timestamp(value: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(value).isoformat(timespec="seconds")
