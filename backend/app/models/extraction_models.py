from __future__ import annotations

from pydantic import BaseModel, Field


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
    templateBinarizedPath: str | None = None
    uploadedBinarizedPath: str | None = None


class OCRWordBoxModel(BaseModel):
    id: int
    text: str
    confidence: float
    bbox: BoundingBoxModel
    matched: bool = False


class ExtractionDebugModel(BaseModel):
    imageWidth: int
    imageHeight: int
    ocrWords: list[OCRWordBoxModel]


class FieldExtractionModel(BaseModel):
    zoneName: str
    text: str
    confidence: float
    bbox: BoundingBoxModel
    warning: str | None = None
    matchedWordIds: list[int] = Field(default_factory=list)


class ExtractResponseModel(BaseModel):
    templateId: str
    ocrEngine: str
    alignment: AlignmentModel
    preview: AlignmentPreviewModel
    debug: ExtractionDebugModel
    fields: list[FieldExtractionModel]
    errors: list[str]
