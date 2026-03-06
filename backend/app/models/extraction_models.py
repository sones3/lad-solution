from __future__ import annotations

from pydantic import BaseModel


class BoundingBoxModel(BaseModel):
    x: int
    y: int
    width: int
    height: int


class AlignmentModel(BaseModel):
    success: bool
    inlierRatio: float
    matchesUsed: int
    warnings: list[str]


class AlignmentPreviewModel(BaseModel):
    templatePath: str
    uploadedPath: str
    alignedPath: str | None = None
    overlayPath: str | None = None


class FieldExtractionModel(BaseModel):
    zoneName: str
    text: str
    confidence: float
    bbox: BoundingBoxModel
    warning: str | None = None


class ExtractResponseModel(BaseModel):
    templateId: str
    alignment: AlignmentModel
    preview: AlignmentPreviewModel
    fields: list[FieldExtractionModel]
    errors: list[str]
