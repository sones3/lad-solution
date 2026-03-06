from __future__ import annotations

from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.models.extraction_models import (
    AlignmentModel,
    AlignmentPreviewModel,
    BoundingBoxModel,
    ExtractionDebugModel,
    ExtractResponseModel,
    FieldExtractionModel,
    OCRWordBoxModel,
)
from app.models.template_models import TemplateModel
from app.services.ocr_service import extract_zone_text_from_words, run_word_ocr
from app.services.orb_align import align_document_to_template
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


def _save_preview_images(
    *,
    template: TemplateModel,
    template_image: np.ndarray,
    input_raw: bytes,
    input_extension: str,
    aligned_image: np.ndarray | None,
    template_store: TemplateStore,
) -> AlignmentPreviewModel:
    run_id = uuid4().hex[:12]
    uploaded_name = f"{template.id}-{run_id}-uploaded{input_extension}"
    uploaded_path = template_store.uploads_dir / uploaded_name
    uploaded_path.write_bytes(input_raw)

    aligned_path_api: str | None = None
    overlay_path_api: str | None = None
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

    return AlignmentPreviewModel(
        templatePath=template.imagePath,
        uploadedPath=f"/data/uploads/{uploaded_name}",
        alignedPath=aligned_path_api,
        overlayPath=overlay_path_api,
    )


@router.post("/extract", response_model=ExtractResponseModel)
def extract_indexes(
    templateId: str = Form(...),
    image: UploadFile = File(...),
    debug: bool = Form(default=False),
    template_store: TemplateStore = Depends(get_store),
) -> ExtractResponseModel:
    template = template_store.get_template(templateId)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template_image = _load_template_image(template, template_store)
    input_image, input_raw, input_extension = _decode_upload(image)

    alignment_result = align_document_to_template(template_image=template_image, input_image=input_image)

    if not alignment_result.success or alignment_result.aligned_image is None:
        preview = _save_preview_images(
            template=template,
            template_image=template_image,
            input_raw=input_raw,
            input_extension=input_extension,
            aligned_image=None,
            template_store=template_store,
        )
        return ExtractResponseModel(
            templateId=template.id,
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

    words, ocr_error = run_word_ocr(alignment_result.aligned_image)

    preview = _save_preview_images(
        template=template,
        template_image=template_image,
        input_raw=input_raw,
        input_extension=input_extension,
        aligned_image=alignment_result.aligned_image,
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

        if zone.required and not text:
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
