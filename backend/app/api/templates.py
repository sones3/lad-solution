from __future__ import annotations

import json

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.models.template_models import (
    DeleteResponse,
    TemplateModel,
    TemplateSummaryModel,
    UpdateTemplatePayload,
    ZoneModel,
    utc_now_iso,
)
from app.storage.template_store import TemplateStore

router = APIRouter(prefix="/templates", tags=["templates"])


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


def _validate_zone_bounds(zones: list[ZoneModel], image_width: int, image_height: int) -> None:
    for zone in zones:
        if zone.x + zone.width > image_width or zone.y + zone.height > image_height:
            raise HTTPException(status_code=400, detail=f"Zone '{zone.name}' is outside template image bounds")


@router.post("", response_model=TemplateModel)
def create_template(
    name: str = Form(...),
    zones: str = Form(...),
    image: UploadFile = File(...),
    template_store: TemplateStore = Depends(get_store),
) -> TemplateModel:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty")

    zone_models = _parse_zones(zones)
    image_array = _image_from_upload(image)
    image_height, image_width = image_array.shape[:2]
    _validate_zone_bounds(zone_models, image_width, image_height)

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
        createdAt=now,
        updatedAt=now,
        version=1,
    )

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

    names = [zone.name for zone in payload.zones]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Zone names must be unique")

    _validate_zone_bounds(payload.zones, current.imageWidth, current.imageHeight)

    updated = current.model_copy(
        update={
            "name": payload.name.strip(),
            "zones": payload.zones,
            "updatedAt": utc_now_iso(),
            "version": current.version + 1,
        }
    )

    return template_store.save_template(updated)


@router.delete("/{template_id}", response_model=DeleteResponse)
def delete_template(template_id: str, template_store: TemplateStore = Depends(get_store)) -> DeleteResponse:
    deleted = template_store.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return DeleteResponse(deleted=True)
