from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ZoneType = Literal["text", "number", "date", "alphanumeric"]
PaperDetectorType = Literal["orb", "surf"]


class ZoneModel(BaseModel):
    id: str
    name: str = Field(min_length=1)
    type: ZoneType = "text"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=10)
    height: int = Field(ge=10)
    required: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Zone name cannot be empty")
        return cleaned


class IgnoreRegionModel(BaseModel):
    id: str
    name: str = Field(min_length=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=10)
    height: int = Field(ge=10)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Ignore region name cannot be empty")
        return cleaned


class PaperFeatureArtifactModel(BaseModel):
    detector: PaperDetectorType = "orb"
    artifactPath: str
    maxKeypoints: int = Field(gt=0)
    epsilon: int = Field(gt=0)
    synthesizedImageCount: int = Field(gt=0)
    buildWidth: int = Field(gt=0)
    buildHeight: int = Field(gt=0)
    createdAt: str
    version: int = 1


class TemplateModel(BaseModel):
    id: str
    name: str = Field(min_length=1)
    imagePath: str
    imageWidth: int
    imageHeight: int
    zones: list[ZoneModel] = Field(default_factory=list)
    paperIgnoreRegions: list[IgnoreRegionModel] = Field(default_factory=list)
    paperFeatureArtifact: PaperFeatureArtifactModel | None = None
    useWolfBinarization: bool = False
    createdAt: str
    updatedAt: str
    version: int = 1

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Template name cannot be empty")
        return cleaned


class TemplateSummaryModel(BaseModel):
    id: str
    name: str
    zoneCount: int
    updatedAt: str
    thumbnailPath: str


class UpdateTemplatePayload(BaseModel):
    name: str
    zones: list[ZoneModel] = Field(default_factory=list)
    paperIgnoreRegions: list[IgnoreRegionModel] = Field(default_factory=list)
    useWolfBinarization: bool = False


class DeleteResponse(BaseModel):
    deleted: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
