from __future__ import annotations

import json
import logging
import sys

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.models.template_models import (
    DeleteResponse,
    IgnoreRegionModel,
    PaperFeatureArtifactModel,
    TemplateModel,
    TemplateSummaryModel,
    UpdateTemplatePayload,
    ZoneModel,
    utc_now_iso,
)
from app.services.template_feature_stability import (
    PAPER_DETECTOR,
    PAPER_EPSILON,
    PAPER_MAX_BUILD_DIMENSION,
    PAPER_MAX_KEYPOINTS,
    PAPER_SYNTHESIZED_IMAGE_COUNT,
    build_stable_paper_template_features,
    prepare_paper_template_inputs,
)
from app.services.template_feature_store import save_paper_template_features
from app.storage.template_store import TemplateStore

router = APIRouter(prefix="/templates", tags=["templates"])
logger = logging.getLogger(__name__)


def _emit_progress(message: str, *args: object) -> None:
    logger.info(message, *args)
    rendered = message % args if args else message
    print(rendered, file=sys.stdout, flush=True)


def get_store() -> TemplateStore:
    from app.main import store

    return store


def _parse_zones(zones_raw: str) -> list[ZoneModel]:
    try:
        decoded = json.loads(zones_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid zones JSON") from exc

    zones = [ZoneModel.model_validate(item) for item in decoded]
    names = [zone.name for zone in zones]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Zone names must be unique")

    return zones


def _parse_ignore_regions(ignore_regions_raw: str | None) -> list[IgnoreRegionModel]:
    if ignore_regions_raw is None or not ignore_regions_raw.strip():
        return []

    try:
        decoded = json.loads(ignore_regions_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid paperIgnoreRegions JSON") from exc

    regions = [IgnoreRegionModel.model_validate(item) for item in decoded]
    names = [region.name for region in regions]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Ignore region names must be unique")
    return regions


def _image_from_upload(file: UploadFile) -> np.ndarray:
    if file.content_type not in {"image/png", "image/jpeg"}:
        raise HTTPException(status_code=400, detail="Only PNG and JPEG files are supported")

    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    image = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Unable to decode image")
    return image


def _validate_region_bounds(
    regions: list[ZoneModel] | list[IgnoreRegionModel],
    *,
    image_width: int,
    image_height: int,
    label: str,
) -> None:
    for region in regions:
        if region.x + region.width > image_width or region.y + region.height > image_height:
            raise HTTPException(status_code=400, detail=f"{label} '{region.name}' is outside template image bounds")


def _build_paper_feature_artifact(
    *,
    template: TemplateModel,
    template_image: np.ndarray,
    template_store: TemplateStore,
) -> PaperFeatureArtifactModel:
    _emit_progress(
        "Building paper artifact for template %s with %d ignore regions and %d synthetic views",
        template.id,
        len(template.paperIgnoreRegions),
        PAPER_SYNTHESIZED_IMAGE_COUNT,
    )
    prepared_template = prepare_paper_template_inputs(
        template_image,
        template.paperIgnoreRegions,
        max_dimension=PAPER_MAX_BUILD_DIMENSION,
    )
    if prepared_template.scale_factor < 1.0:
        _emit_progress(
            "[%s] Downscaled paper build image from %dx%d to %dx%d (scale %.3f)",
            template.id,
            template_image.shape[1],
            template_image.shape[0],
            prepared_template.image.shape[1],
            prepared_template.image.shape[0],
            prepared_template.scale_factor,
        )

    def log_progress(stage: str, current: int, total: int) -> None:
        if stage == "detect_template_keypoints":
            _emit_progress("[%s] Detecting template keypoints", template.id)
            return
        if stage == "select_top_keypoints":
            _emit_progress("[%s] Selecting top stable keypoints", template.id)
            return
        percent = 0 if total <= 0 else int((current / total) * 100)
        _emit_progress("[%s] Paper artifact progress: %d%% (%d/%d synthetic views)", template.id, percent, current, total)

    stable_features = build_stable_paper_template_features(
        prepared_template.image,
        ignore_regions=prepared_template.ignore_regions,
        max_keypoints=PAPER_MAX_KEYPOINTS,
        epsilon=PAPER_EPSILON,
        synthesized_image_count=PAPER_SYNTHESIZED_IMAGE_COUNT,
        progress_callback=log_progress,
    )
    artifact_path = save_paper_template_features(
        template_store.template_features_dir,
        template_id=template.id,
        keypoints=stable_features.keypoints,
        descriptors=stable_features.descriptors,
        stability=stable_features.stability,
    )
    artifact = PaperFeatureArtifactModel(
        detector=PAPER_DETECTOR,
        artifactPath=artifact_path,
        maxKeypoints=len(stable_features.keypoints),
        epsilon=PAPER_EPSILON,
        synthesizedImageCount=PAPER_SYNTHESIZED_IMAGE_COUNT,
        buildWidth=prepared_template.image.shape[1],
        buildHeight=prepared_template.image.shape[0],
        createdAt=utc_now_iso(),
        version=1,
    )
    _emit_progress(
        "Finished paper artifact for template %s: selected %d keypoints, saved to %s",
        template.id,
        len(stable_features.keypoints),
        artifact_path,
    )
    return artifact


def _load_saved_template_image(template: TemplateModel, template_store: TemplateStore) -> np.ndarray:
    image_path = template_store.data_dir.parent / template.imagePath.removeprefix("/")
    image = cv2.imread(str(image_path))
    if image is None:
        raise HTTPException(status_code=500, detail="Failed to read saved template image")
    return image


@router.post("", response_model=TemplateModel)
def create_template(
    name: str = Form(...),
    zones: str = Form(...),
    paperIgnoreRegions: str = Form(default="[]"),
    useWolfBinarization: bool = Form(default=False),
    image: UploadFile = File(...),
    template_store: TemplateStore = Depends(get_store),
) -> TemplateModel:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty")

    _emit_progress("Starting template creation for '%s'", cleaned_name)

    zone_models = _parse_zones(zones)
    ignore_region_models = _parse_ignore_regions(paperIgnoreRegions)
    image_array = _image_from_upload(image)
    image_height, image_width = image_array.shape[:2]
    _validate_region_bounds(zone_models, image_width=image_width, image_height=image_height, label="Zone")
    _validate_region_bounds(
        ignore_region_models,
        image_width=image_width,
        image_height=image_height,
        label="Ignore region",
    )

    template_id = template_store.next_template_id()
    extension = ".jpg" if image.content_type == "image/jpeg" else ".png"
    image_file_name = f"{template_id}{extension}"
    image_file_path = template_store.template_images_dir / image_file_name

    encoded_ok, encoded = cv2.imencode(extension, image_array)
    if not encoded_ok:
        raise HTTPException(status_code=500, detail="Unable to encode template image")
    image_file_path.write_bytes(encoded.tobytes())

    now = utc_now_iso()
    template = TemplateModel(
        id=template_id,
        name=cleaned_name,
        imagePath=f"/data/template_images/{image_file_name}",
        imageWidth=image_width,
        imageHeight=image_height,
        zones=zone_models,
        paperIgnoreRegions=ignore_region_models,
        useWolfBinarization=useWolfBinarization,
        createdAt=now,
        updatedAt=now,
        version=1,
    )

    try:
        template = template.model_copy(
            update={
                "paperFeatureArtifact": _build_paper_feature_artifact(
                    template=template,
                    template_image=image_array,
                    template_store=template_store,
                )
            }
        )
    except RuntimeError as exc:
        if image_file_path.exists():
            image_file_path.unlink()
        logger.exception("Template creation failed for '%s'", cleaned_name)
        print(f"Template creation failed for '{cleaned_name}'", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _emit_progress("Template creation complete for '%s' (%s)", cleaned_name, template.id)
    return template_store.save_template(template)


@router.get("", response_model=list[TemplateSummaryModel])
def list_templates(template_store: TemplateStore = Depends(get_store)) -> list[TemplateSummaryModel]:
    templates = sorted(template_store.list_templates(), key=lambda item: item.updatedAt, reverse=True)
    return [
        TemplateSummaryModel(
            id=template.id,
            name=template.name,
            zoneCount=len(template.zones),
            updatedAt=template.updatedAt,
            thumbnailPath=template.imagePath,
        )
        for template in templates
    ]


@router.get("/{template_id}", response_model=TemplateModel)
def get_template(template_id: str, template_store: TemplateStore = Depends(get_store)) -> TemplateModel:
    template = template_store.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/{template_id}", response_model=TemplateModel)
def update_template(
    template_id: str,
    payload: UpdateTemplatePayload,
    template_store: TemplateStore = Depends(get_store),
) -> TemplateModel:
    current = template_store.get_template(template_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Template not found")

    _emit_progress("Starting template update for '%s' (%s)", current.name, current.id)

    names = [zone.name for zone in payload.zones]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Zone names must be unique")

    ignore_region_names = [region.name for region in payload.paperIgnoreRegions]
    if len(ignore_region_names) != len(set(ignore_region_names)):
        raise HTTPException(status_code=400, detail="Ignore region names must be unique")

    _validate_region_bounds(payload.zones, image_width=current.imageWidth, image_height=current.imageHeight, label="Zone")
    _validate_region_bounds(
        payload.paperIgnoreRegions,
        image_width=current.imageWidth,
        image_height=current.imageHeight,
        label="Ignore region",
    )

    updated_base = current.model_copy(
        update={
            "name": payload.name.strip(),
            "zones": payload.zones,
            "paperIgnoreRegions": payload.paperIgnoreRegions,
            "useWolfBinarization": payload.useWolfBinarization,
            "updatedAt": utc_now_iso(),
            "version": current.version + 1,
        }
    )

    try:
        updated = updated_base.model_copy(
            update={
                "paperFeatureArtifact": _build_paper_feature_artifact(
                    template=updated_base,
                    template_image=_load_saved_template_image(current, template_store),
                    template_store=template_store,
                )
            }
        )
    except RuntimeError as exc:
        logger.exception("Template update failed for '%s' (%s)", current.name, current.id)
        print(f"Template update failed for '{current.name}' ({current.id})", file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _emit_progress("Template update complete for '%s' (%s)", updated.name, updated.id)
    return template_store.save_template(updated)


@router.delete("/{template_id}", response_model=DeleteResponse)
def delete_template(template_id: str, template_store: TemplateStore = Depends(get_store)) -> DeleteResponse:
    deleted = template_store.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return DeleteResponse(deleted=True)
