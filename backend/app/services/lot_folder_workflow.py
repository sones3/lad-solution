from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import shutil
import uuid

import cv2

from app.models.template_models import TemplateModel
from app.services.lot_csv import parse_lot_csv
from app.services.lot_reconciliation import (
    ReconciliationDocumentInput,
    build_reconciliation,
)
from app.services.lot_separator import (
    LotSeparatorConfig,
    iter_lot_pdf_pages_with_paper,
    ocr_lot_page,
)
from app.services.lot_splitter import write_split_pdfs
from app.services.lot_workbook import write_reconciliation_workbook
from app.services.pdf_render import get_pdf_page_count, render_pdf_page
from app.services.template_feature_store import load_paper_template_features
from app.services.lot_workspace import LotWorkspace, save_lot_workspace_config
from app.storage.template_store import TemplateStore


def process_lot_workspace(
    *,
    workspace: LotWorkspace,
    template_id: str,
    paper_threshold: float,
    template_store: TemplateStore,
) -> Iterator[dict[str, object]]:
    if workspace.status != "ready":
        raise ValueError("Selected lot is incomplete and cannot be processed")

    pdf_bytes = workspace.pdf_path.read_bytes()
    csv_rows = parse_lot_csv(workspace.csv_path.read_bytes())
    template = template_store.get_template(template_id)
    if template is None:
        raise ValueError("Template not found")
    if template.paperFeatureArtifact is None:
        raise ValueError("Selected template does not have a paper artifact")

    artifact_path = (
        template_store.data_dir.parent
        / template.paperFeatureArtifact.artifactPath.removeprefix("/")
    )
    if not artifact_path.exists():
        raise ValueError("Paper template artifact file does not exist")
    template_features = load_paper_template_features(artifact_path)
    template_image = _load_template_image(
        template=template, template_store=template_store
    )

    config = LotSeparatorConfig(
        separation_method="paper",
        template_id=template_id,
        paper_threshold=paper_threshold,
    )
    save_lot_workspace_config(
        workspace, template_id=template_id, paper_threshold=paper_threshold
    )

    archive_dir: str | None = None
    build_dir = (
        workspace.path
        / f".lad-build-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    build_sep_dir = build_dir / "sep"
    build_workbook_path = build_dir / workspace.workbook_path.name
    total_pages = get_pdf_page_count(pdf_bytes)

    yield {
        "type": "started",
        "lotName": workspace.name,
        "templateId": template_id,
        "paperThreshold": paper_threshold,
    }

    try:
        archive_message = "No previous outputs to archive"
        if workspace.outputs_exist:
            archive_dir = _archive_existing_outputs(workspace)
            archive_message = "Archived previous outputs"
        yield {
            "type": "step",
            "step": "archive_previous_outputs",
            "message": archive_message,
        }

        page_diagnostics = []
        for page_index, page in enumerate(
            iter_lot_pdf_pages_with_paper(
                pdf_bytes,
                config=config,
                template=template,
                template_image=template_image,
                template_features=template_features,
            ),
            start=1,
        ):
            page_diagnostics.append(page)
            if _should_emit_progress(page_index, total_pages):
                yield {
                    "type": "progress",
                    "stage": "analyze_source_pdf",
                    "current": page_index,
                    "total": total_pages,
                    "message": f"Analyzed {page_index}/{total_pages} source pages",
                }
        page_diagnostics.sort(key=lambda page: page.pageNumber)
        start_pages = sorted(
            page.pageNumber for page in page_diagnostics if page.isNewDocument
        )
        split_documents = write_split_pdfs(
            pdf_bytes, output_dir=build_sep_dir, start_pages=start_pages
        )
        yield {
            "type": "step",
            "step": "split_source_pdf",
            "message": f"Generated {len(split_documents)} split PDFs",
        }

        reconciliation_workers = max(1, min(config.workers, len(split_documents) or 1))
        with ThreadPoolExecutor(max_workers=reconciliation_workers) as executor:
            futures = {
                executor.submit(
                    _build_reconciliation_document,
                    config=config,
                    pdf_bytes=pdf_bytes,
                    split_document=split_document,
                ): split_document.file_name
                for split_document in split_documents
            }
            reconciliation_documents = []
            completed_documents = 0
            for future in as_completed(futures):
                reconciliation_documents.append(future.result())
                completed_documents += 1
                if _should_emit_progress(completed_documents, len(split_documents)):
                    yield {
                        "type": "progress",
                        "stage": "ocr_split_documents",
                        "current": completed_documents,
                        "total": len(split_documents),
                        "message": f"OCR processed {completed_documents}/{len(split_documents)} split PDFs",
                    }
        reconciliation_documents.sort(key=lambda document: document.start_page)
        yield {
            "type": "step",
            "step": "run_matching",
            "message": f"Matching {len(csv_rows)} CSV rows against {len(reconciliation_documents)} split PDFs",
        }
        reconciliation_result = build_reconciliation(
            csv_rows=csv_rows, documents=reconciliation_documents
        )
        yield {
            "type": "step",
            "step": "run_matching",
            "message": "Built CSV-to-PDF assignments",
        }

        build_dir.mkdir(parents=True, exist_ok=True)
        write_reconciliation_workbook(
            output_path=build_workbook_path,
            lot_name=workspace.name,
            template_name=template.name,
            paper_threshold=paper_threshold,
            result=reconciliation_result,
            page_diagnostics=page_diagnostics,
        )
        yield {
            "type": "step",
            "step": "generate_workbook",
            "message": "Generated reconciliation workbook",
        }

        shutil.move(str(build_sep_dir), str(workspace.sep_dir))
        shutil.move(str(build_workbook_path), str(workspace.workbook_path))
        shutil.rmtree(build_dir, ignore_errors=True)

        yield {
            "type": "complete",
            "summary": {
                "generatedPdfCount": reconciliation_result.summary.generated_pdf_count,
                "csvRowCount": reconciliation_result.summary.csv_row_count,
                "autoAssignedCount": reconciliation_result.summary.auto_assigned_count,
                "needsVerificationCount": reconciliation_result.summary.needs_verification_count,
                "ambiguousCount": reconciliation_result.summary.ambiguous_count,
                "missingPdfCount": reconciliation_result.summary.missing_pdf_count,
            },
        }
    except Exception:
        shutil.rmtree(build_dir, ignore_errors=True)
        if archive_dir is not None:
            _restore_archived_outputs(
                workspace=workspace, archive_dir=workspace.path / archive_dir
            )
        raise


def _build_reconciliation_document(
    *, config: LotSeparatorConfig, pdf_bytes: bytes, split_document
) -> ReconciliationDocumentInput:
    image = render_pdf_page(
        pdf_bytes, page_number=split_document.start_page, dpi=config.dpi
    )
    ocr_page = ocr_lot_page(
        page_number=split_document.start_page, image=image, config=config
    )
    return ReconciliationDocumentInput(
        file_name=split_document.file_name,
        start_page=split_document.start_page,
        end_page=split_document.end_page,
        page_count=split_document.page_count,
        first_page_raw=ocr_page.ocrTextRaw,
        first_page_normalized=ocr_page.ocrTextNormalized,
        first_page_compact=ocr_page.ocrTextCompact,
    )


def _archive_existing_outputs(workspace: LotWorkspace) -> str:
    archive_root = workspace.path / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_name = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = archive_root / archive_name
    archive_dir.mkdir(parents=True, exist_ok=False)

    if workspace.sep_dir.exists():
        shutil.move(str(workspace.sep_dir), str(archive_dir / "sep"))
    if workspace.workbook_path.exists():
        shutil.move(
            str(workspace.workbook_path),
            str(archive_dir / workspace.workbook_path.name),
        )
    return str(archive_dir.relative_to(workspace.path))


def _restore_archived_outputs(*, workspace: LotWorkspace, archive_dir) -> None:
    archived_sep = archive_dir / "sep"
    archived_workbook = archive_dir / workspace.workbook_path.name
    if archived_sep.exists() and not workspace.sep_dir.exists():
        shutil.move(str(archived_sep), str(workspace.sep_dir))
    if archived_workbook.exists() and not workspace.workbook_path.exists():
        shutil.move(str(archived_workbook), str(workspace.workbook_path))


def _load_template_image(*, template: TemplateModel, template_store: TemplateStore):
    image_path = template_store.data_dir.parent / template.imagePath.removeprefix("/")
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("Template image file does not exist")
    return image


def _should_emit_progress(current: int, total: int) -> bool:
    if total <= 0:
        return False
    if current == total:
        return True
    if total <= 20:
        return True
    if current <= 5:
        return True
    return current % 10 == 0
