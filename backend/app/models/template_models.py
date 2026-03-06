from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ZoneType = Literal["text", "number", "date", "alphanumeric"]


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


class TemplateModel(BaseModel):
    id: str
    name: str = Field(min_length=1)
    imagePath: str
    imageWidth: int
    imageHeight: int
    zones: list[ZoneModel]
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
    zones: list[ZoneModel]


class DeleteResponse(BaseModel):
    deleted: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
