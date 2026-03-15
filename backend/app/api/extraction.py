from __future__ import annotations

from collections.abc import Iterator
import json
from typing import cast
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.models.extraction_models import (
    AlignmentModel,
    AlignmentPreviewModel,
    BoundingBoxModel,
    ExtractionDebugModel,
    ExtractResponseModel,
    FieldExtractionModel,
    LogicalDocumentRangeModel,
    LogicalSeparationPageMatchModel,
    LogicalSeparationResponseModel,
    OCRWordBoxModel,
)
from app.models.template_models import TemplateModel
from app.services.paper_align import align_document_with_paper_features
from app.services.binarization import to_bgr, wolf_binarize
from app.services.hybrid_detector import detect_with_hybrid, prepare_hybrid_template
from app.services.ocr_service import OCREngine, extract_zone_text_from_words, run_word_ocr
from app.services.orb_align import align_document_to_template
from app.services.paddle_engine import get_paddle_ocr
from app.services.pdf_render import render_pdf_pages
from app.services.template_feature_store import load_paper_template_features
from app.storage.template_store import TemplateStore

router = APIRouter(tags=["extraction"])


def get_store() -> TemplateStore:
    from app.main import store

    return store


def _decode_upload(file: UploadFile) -> tuple[np.ndarray, bytes, str]:
    if file.content_type not in {"image/png", "image/jpeg"}:
        raise HTTPException(status_code=400, detail="Only PNG and JPEG files are supported")

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Unable to decode image")

    extension = ".jpg" if file.content_type == "image/jpeg" else ".png"
    return image, raw, extension


def _load_template_image(template: TemplateModel, template_store: TemplateStore) -> np.ndarray:
    image_path = template_store.data_dir.parent / template.imagePath.removeprefix("/")
    if not image_path.exists():
        raise HTTPException(status_code=500, detail="Template image file does not exist")

    image = cv2.imread(str(image_path))
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read template image")
    return image


def _decode_pdf_upload(file: UploadFile) -> bytes:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return raw


def _parse_separation_method(method: str) -> str:
    normalized = method.strip().lower()
    if normalized == "visual-structural":
        normalized = "hybrid"
    if normalized not in {"orb", "hybrid", "paper"}:
        raise HTTPException(status_code=400, detail="method must be 'orb', 'hybrid', or 'paper'")
    return normalized


def _parse_separation_threshold(*, method: str, threshold: float | None) -> float:
    if threshold is None:
        if method == "hybrid":
            return 0.55
        return 0.35
    if not 0.0 <= threshold <= 1.0:
        raise HTTPException(status_code=400, detail="threshold must be between 0.0 and 1.0")
    return threshold


def _compute_orb_confirmation(*, success: bool, inlier_ratio: float, matches_used: int) -> float:
    if not success:
        return 0.0

    normalized_matches = min(matches_used / 40.0, 1.0)
    return max(0.0, min(1.0, (inlier_ratio * 0.75) + (normalized_matches * 0.25)))


def _prepare_input_for_alignment(*, use_binarization: bool, input_image: np.ndarray) -> tuple[np.ndarray, str | None]:
    input_for_alignment = input_image
    binarization_warning: str | None = None

    if use_binarization:
        try:
            input_for_alignment = to_bgr(wolf_binarize(input_image))
        except RuntimeError as exc:
            binarization_warning = str(exc)

    return input_for_alignment, binarization_warning


def _prepare_template_for_logical_separation(
    template: TemplateModel, template_image: np.ndarray
) -> tuple[np.ndarray, bool, list[str]]:
    warnings: list[str] = []
    if not template.useWolfBinarization:
        return template_image, False, warnings

    try:
        return to_bgr(wolf_binarize(template_image)), True, warnings
    except RuntimeError as exc:
        warnings.append(str(exc))
        return template_image, False, warnings


def _build_documents(start_pages: list[int], total_pages: int) -> list[LogicalDocumentRangeModel]:
    documents: list[LogicalDocumentRangeModel] = []
    for index, start_page in enumerate(start_pages, start=1):
        next_start = start_pages[index] if index < len(start_pages) else None
        end_page = total_pages if next_start is None else next_start - 1
        documents.append(
            LogicalDocumentRangeModel(
                index=index,
                startPage=start_page,
                endPage=end_page,
                pageCount=(end_page - start_page) + 1,
            )
        )
    return documents


def _iter_logical_separation_events(
    *,
    template: TemplateModel,
    template_store: TemplateStore,
    pdf_raw: bytes,
    method: str,
    threshold: float,
) -> Iterator[dict[str, object]]:
    template_image = _load_template_image(template, template_store)
    warnings: list[str] = []
    template_binarized = False
    prepared_hybrid_template = None
    paper_template_features = None
    paper_artifact = None
    template_for_alignment = template_image
    render_dpi = 144

    if method == "orb":
        template_for_alignment, template_binarized, warnings = _prepare_template_for_logical_separation(
            template, template_image
        )
    elif method == "hybrid":
        render_dpi = 200
        template_for_alignment, template_binarized, warnings = _prepare_template_for_logical_separation(
            template, template_image
        )
        try:
            prepared_hybrid_template = prepare_hybrid_template(template_image)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        if template.paperFeatureArtifact is None:
            raise HTTPException(status_code=500, detail="Paper-method template features are unavailable")
        paper_artifact = template.paperFeatureArtifact
        template_for_alignment = cv2.resize(
            template_image,
            (
                paper_artifact.buildWidth,
                paper_artifact.buildHeight,
            ),
            interpolation=cv2.INTER_AREA,
        )
        artifact_path = template_store.data_dir.parent / paper_artifact.artifactPath.removeprefix("/")
        if not artifact_path.exists():
            raise HTTPException(status_code=500, detail="Paper-method feature artifact does not exist")
        try:
            paper_template_features = load_paper_template_features(artifact_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Failed to load paper-method feature artifact") from exc

    yield {
        "type": "started",
        "templateId": template.id,
        "method": method,
        "threshold": threshold,
        "templateBinarized": template_binarized,
    }

    matched_start_pages: list[int] = []
    page_matches: list[LogicalSeparationPageMatchModel] = []
    errors: list[str] = []
    total_pages = 0

    try:
        for page_number, page_image in render_pdf_pages(pdf_raw, dpi=render_dpi):
            total_pages = page_number
            if method == "orb":
                input_for_alignment, binarization_warning = _prepare_input_for_alignment(
                    use_binarization=template_binarized,
                    input_image=page_image,
                )
                page_binarized = template_binarized and binarization_warning is None
                alignment_result = align_document_to_template(
                    template_image=template_for_alignment,
                    input_image=input_for_alignment,
                    warp=False,
                )

                page_warnings = list(alignment_result.warnings)
                if binarization_warning:
                    page_warnings.append(binarization_warning)

                score = alignment_result.inlier_ratio if alignment_result.success else 0.0
                matched = alignment_result.success and alignment_result.inlier_ratio >= threshold
                page_match = LogicalSeparationPageMatchModel(
                    pageNumber=page_number,
                    matched=matched,
                    method=method,
                    binarized=page_binarized,
                    score=score,
                    inlierRatio=alignment_result.inlier_ratio,
                    matchesUsed=alignment_result.matches_used,
                    visualScore=None,
                    orbScore=score,
                    warnings=page_warnings,
                    error=alignment_result.error,
                )
            elif method == "paper":
                if paper_template_features is None or paper_artifact is None:
                    raise HTTPException(status_code=500, detail="Paper-method features are unavailable")

                input_for_alignment = cv2.resize(
                    page_image,
                    (
                        paper_artifact.buildWidth,
                        paper_artifact.buildHeight,
                    ),
                    interpolation=cv2.INTER_AREA,
                )
                page_binarized = False
                alignment_result = align_document_with_paper_features(
                    template_image=template_for_alignment,
                    template_features=paper_template_features,
                    input_image=input_for_alignment,
                    warp=False,
                )
                page_warnings = list(alignment_result.warnings)

                score = alignment_result.inlier_ratio if alignment_result.success else 0.0
                matched = alignment_result.success and alignment_result.inlier_ratio >= threshold
                page_match = LogicalSeparationPageMatchModel(
                    pageNumber=page_number,
                    matched=matched,
                    method=method,
                    binarized=page_binarized,
                    score=score,
                    inlierRatio=alignment_result.inlier_ratio,
                    matchesUsed=alignment_result.matches_used,
                    visualScore=None,
                    orbScore=None,
                    warnings=page_warnings,
                    error=alignment_result.error,
                )
            else:
                if prepared_hybrid_template is None:
                    raise HTTPException(status_code=500, detail="Hybrid template is unavailable")

                precheck = detect_with_hybrid(
                    prepared_hybrid_template,
                    page_image,
                    orb_confirmation=0.0,
                    threshold=threshold,
                    evaluate_orb_gate=False,
                )
                page_warnings = list(precheck.warnings)
                alignment_result = None
                orb_score = 0.0
                page_binarized = False
                if precheck.visual_score >= max(0.30, threshold - 0.15):
                    input_for_alignment, binarization_warning = _prepare_input_for_alignment(
                        use_binarization=template_binarized,
                        input_image=page_image,
                    )
                    page_binarized = template_binarized and binarization_warning is None
                    alignment_result = align_document_to_template(
                        template_image=template_for_alignment,
                        input_image=input_for_alignment,
                        warp=False,
                    )
                    orb_score = _compute_orb_confirmation(
                        success=alignment_result.success,
                        inlier_ratio=alignment_result.inlier_ratio,
                        matches_used=alignment_result.matches_used,
                    )
                    if binarization_warning:
                        page_warnings.append(binarization_warning)
                    page_warnings.extend(alignment_result.warnings)
                else:
                    page_warnings.append("Skipped ORB confirmation because anchor score was below gate")

                detection_result = detect_with_hybrid(
                    prepared_hybrid_template,
                    page_image,
                    orb_confirmation=orb_score,
                    threshold=threshold,
                )
                page_warnings.extend(detection_result.warnings)

                matched = (
                    detection_result.final_score >= threshold
                    and detection_result.visual_score >= max(0.30, threshold - 0.15)
                    and detection_result.critical_score >= max(0.33, threshold - 0.10)
                    and detection_result.orb_score >= max(0.18, threshold - 0.25)
                )
                page_match = LogicalSeparationPageMatchModel(
                    pageNumber=page_number,
                    matched=matched,
                    method=method,
                    binarized=page_binarized,
                    score=detection_result.final_score,
                    inlierRatio=alignment_result.inlier_ratio if alignment_result is not None else None,
                    matchesUsed=alignment_result.matches_used if alignment_result is not None else None,
                    visualScore=detection_result.visual_score,
                    orbScore=detection_result.orb_score,
                    warnings=list(dict.fromkeys(page_warnings)),
                    error=alignment_result.error if alignment_result is not None else None,
                )

            if matched:
                matched_start_pages.append(page_number)

            page_matches.append(page_match)
            yield {"type": "page", "pageMatch": page_match.model_dump(mode="json")}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if total_pages == 0:
        raise HTTPException(status_code=400, detail="PDF does not contain any pages")

    if not matched_start_pages:
        warnings.append("No template start pages detected")

    yield {
        "type": "complete",
        "result": LogicalSeparationResponseModel(
            templateId=template.id,
            method=method,
            threshold=threshold,
            totalPages=total_pages,
            matchedStartPages=matched_start_pages,
            documents=_build_documents(matched_start_pages, total_pages),
            pageMatches=page_matches,
            warnings=warnings,
            errors=errors,
        ).model_dump(mode="json"),
    }


def _save_preview_images(
    *,
    template: TemplateModel,
    template_image: np.ndarray,
    input_raw: bytes,
    input_extension: str,
    aligned_image: np.ndarray | None,
    template_binarized: np.ndarray | None,
    uploaded_binarized: np.ndarray | None,
    template_store: TemplateStore,
) -> AlignmentPreviewModel:
    run_id = uuid4().hex[:12]
    uploaded_name = f"{template.id}-{run_id}-uploaded{input_extension}"
    uploaded_path = template_store.uploads_dir / uploaded_name
    uploaded_path.write_bytes(input_raw)

    aligned_path_api: str | None = None
    overlay_path_api: str | None = None
    template_binarized_path_api: str | None = None
    uploaded_binarized_path_api: str | None = None
    if aligned_image is not None:
        aligned_name = f"{template.id}-{run_id}-aligned.png"
        aligned_path = template_store.debug_dir / aligned_name
        cv2.imwrite(str(aligned_path), aligned_image)
        aligned_path_api = f"/data/debug/{aligned_name}"

        overlay = cv2.addWeighted(template_image, 0.5, aligned_image, 0.5, 0)
        overlay_name = f"{template.id}-{run_id}-overlay.png"
        overlay_path = template_store.debug_dir / overlay_name
        cv2.imwrite(str(overlay_path), overlay)
        overlay_path_api = f"/data/debug/{overlay_name}"

    if template_binarized is not None:
        template_bin_name = f"{template.id}-{run_id}-template-binarized.png"
        template_bin_path = template_store.debug_dir / template_bin_name
        cv2.imwrite(str(template_bin_path), template_binarized)
        template_binarized_path_api = f"/data/debug/{template_bin_name}"

    if uploaded_binarized is not None:
        uploaded_bin_name = f"{template.id}-{run_id}-uploaded-binarized.png"
        uploaded_bin_path = template_store.debug_dir / uploaded_bin_name
        cv2.imwrite(str(uploaded_bin_path), uploaded_binarized)
        uploaded_binarized_path_api = f"/data/debug/{uploaded_bin_name}"

    return AlignmentPreviewModel(
        templatePath=template.imagePath,
        uploadedPath=f"/data/uploads/{uploaded_name}",
        alignedPath=aligned_path_api,
        overlayPath=overlay_path_api,
        templateBinarizedPath=template_binarized_path_api,
        uploadedBinarizedPath=uploaded_binarized_path_api,
    )


@router.post("/extract", response_model=ExtractResponseModel)
def extract_indexes(
    templateId: str = Form(...),
    image: UploadFile = File(...),
    ocrEngine: str = Form(default="tesseract"),
    debug: bool = Form(default=False),
    template_store: TemplateStore = Depends(get_store),
) -> ExtractResponseModel:
    selected_ocr_engine_raw = ocrEngine.strip().lower()
    if selected_ocr_engine_raw not in {"tesseract", "paddleocr"}:
        raise HTTPException(status_code=400, detail="ocrEngine must be 'tesseract' or 'paddleocr'")
    selected_ocr_engine = cast(OCREngine, selected_ocr_engine_raw)

    template = template_store.get_template(templateId)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template_image = _load_template_image(template, template_store)
    input_image, input_raw, input_extension = _decode_upload(image)

    template_binarized: np.ndarray | None = None
    uploaded_binarized: np.ndarray | None = None
    template_for_alignment = template_image
    input_for_alignment = input_image
    binarization_warning: str | None = None

    if template.useWolfBinarization:
        try:
            template_binarized = wolf_binarize(template_image)
            uploaded_binarized = wolf_binarize(input_image)
            template_for_alignment = to_bgr(template_binarized)
            input_for_alignment = to_bgr(uploaded_binarized)
        except RuntimeError as exc:
            binarization_warning = str(exc)

    alignment_result = align_document_to_template(
        template_image=template_for_alignment,
        input_image=input_for_alignment,
    )
    if binarization_warning:
        alignment_result.warnings.append(binarization_warning)

    if not alignment_result.success or alignment_result.aligned_image is None:
        preview = _save_preview_images(
            template=template,
            template_image=template_for_alignment,
            input_raw=input_raw,
            input_extension=input_extension,
            aligned_image=None,
            template_binarized=template_binarized,
            uploaded_binarized=uploaded_binarized,
            template_store=template_store,
        )
        return ExtractResponseModel(
            templateId=template.id,
            ocrEngine=selected_ocr_engine,
            alignment=AlignmentModel(
                success=False,
                inlierRatio=alignment_result.inlier_ratio,
                matchesUsed=alignment_result.matches_used,
                warnings=alignment_result.warnings,
            ),
            preview=preview,
            debug=ExtractionDebugModel(imageWidth=0, imageHeight=0, ocrWords=[]),
            fields=[],
            errors=[alignment_result.error or "Alignment failed"],
        )

    if debug:
        debug_name = f"{template.id}-aligned-{uuid4().hex[:12]}.png"
        debug_path = template_store.debug_dir / debug_name
        cv2.imwrite(str(debug_path), alignment_result.aligned_image)

    paddle_ocr, paddle_init_error = get_paddle_ocr()
    words, ocr_error = run_word_ocr(
        alignment_result.aligned_image,
        engine=selected_ocr_engine,
        paddle_ocr=paddle_ocr,
        paddle_init_error=paddle_init_error,
    )

    preview = _save_preview_images(
        template=template,
        template_image=template_for_alignment,
        input_raw=input_raw,
        input_extension=input_extension,
        aligned_image=alignment_result.aligned_image,
        template_binarized=template_binarized,
        uploaded_binarized=uploaded_binarized,
        template_store=template_store,
    )
    matched_word_ids: set[int] = set()

    fields: list[FieldExtractionModel] = []
    errors: list[str] = []
    if ocr_error:
        errors.append(ocr_error)

    for zone in template.zones:
        if ocr_error:
            zone_result = ("", 0.0, ocr_error, [])
        else:
            zone_result = extract_zone_text_from_words(zone=zone, words=words)

        text, confidence, warning, zone_word_ids = zone_result
        matched_word_ids.update(zone_word_ids)

        if not ocr_error and zone.required and not text:
            errors.append(f"Required field '{zone.name}' is empty")

        fields.append(
            FieldExtractionModel(
                zoneName=zone.name,
                text=text,
                confidence=confidence,
                bbox=BoundingBoxModel(
                    x=zone.x,
                    y=zone.y,
                    width=zone.width,
                    height=zone.height,
                ),
                warning=warning,
                matchedWordIds=zone_word_ids,
            )
        )

    image_height, image_width = alignment_result.aligned_image.shape[:2]
    debug_payload = ExtractionDebugModel(
        imageWidth=image_width,
        imageHeight=image_height,
        ocrWords=[
            OCRWordBoxModel(
                id=word.id,
                text=word.text,
                confidence=word.confidence,
                bbox=BoundingBoxModel(x=word.x, y=word.y, width=word.width, height=word.height),
                matched=word.id in matched_word_ids,
            )
            for word in words
        ],
    )

    return ExtractResponseModel(
        templateId=template.id,
        ocrEngine=selected_ocr_engine,
        alignment=AlignmentModel(
            success=True,
            inlierRatio=alignment_result.inlier_ratio,
            matchesUsed=alignment_result.matches_used,
            warnings=alignment_result.warnings,
        ),
        preview=preview,
        debug=debug_payload,
        fields=fields,
        errors=errors,
    )


@router.post("/separate-logically", response_model=LogicalSeparationResponseModel)
def separate_pdf_logically(
    templateId: str = Form(...),
    pdf: UploadFile = File(...),
    method: str = Form(default="orb"),
    threshold: float | None = Form(default=None),
    template_store: TemplateStore = Depends(get_store),
) -> LogicalSeparationResponseModel:
    template = template_store.get_template(templateId)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    pdf_raw = _decode_pdf_upload(pdf)
    selected_method = _parse_separation_method(method)
    selected_threshold = _parse_separation_threshold(method=selected_method, threshold=threshold)
    for event in _iter_logical_separation_events(
        template=template,
        template_store=template_store,
        pdf_raw=pdf_raw,
        method=selected_method,
        threshold=selected_threshold,
    ):
        if event["type"] == "complete":
            return LogicalSeparationResponseModel.model_validate(event["result"])

    raise HTTPException(status_code=500, detail="Logical separation did not complete")


@router.post("/separate-logically/stream")
def separate_pdf_logically_stream(
    templateId: str = Form(...),
    pdf: UploadFile = File(...),
    method: str = Form(default="orb"),
    threshold: float | None = Form(default=None),
    template_store: TemplateStore = Depends(get_store),
) -> StreamingResponse:
    template = template_store.get_template(templateId)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    pdf_raw = _decode_pdf_upload(pdf)
    selected_method = _parse_separation_method(method)
    selected_threshold = _parse_separation_threshold(method=selected_method, threshold=threshold)

    def stream() -> Iterator[bytes]:
        try:
            for event in _iter_logical_separation_events(
                template=template,
                template_store=template_store,
                pdf_raw=pdf_raw,
                method=selected_method,
                threshold=selected_threshold,
            ):
                yield (json.dumps(event) + "\n").encode("utf-8")
        except HTTPException as exc:
            yield (json.dumps({"type": "error", "error": str(exc.detail)}) + "\n").encode("utf-8")

    return StreamingResponse(stream(), media_type="application/x-ndjson")
