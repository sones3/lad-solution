from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from app.models.template_models import TemplateModel


class TemplateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.templates_file = data_dir / "templates.json"
        self.template_images_dir = data_dir / "template_images"
        self.template_features_dir = data_dir / "template_features"
        self.uploads_dir = data_dir / "uploads"
        self.debug_dir = data_dir / "debug"
        self._init_storage()

    def _init_storage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.template_images_dir.mkdir(parents=True, exist_ok=True)
        self.template_features_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)

        if not self.templates_file.exists():
            self._write_json([])

    def _read_json(self) -> list[dict]:
        try:
            return json.loads(self.templates_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _write_json(self, payload: list[dict]) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.data_dir, delete=False) as temp:
            json.dump(payload, temp, indent=2)
            temp.flush()
            Path(temp.name).replace(self.templates_file)

    def list_templates(self) -> list[TemplateModel]:
        return [TemplateModel.model_validate(item) for item in self._read_json()]

    def get_template(self, template_id: str) -> TemplateModel | None:
        for item in self._read_json():
            if item.get("id") == template_id:
                return TemplateModel.model_validate(item)
        return None

    def save_template(self, template: TemplateModel) -> TemplateModel:
        templates = self._read_json()
        updated = False
        for index, item in enumerate(templates):
            if item.get("id") == template.id:
                templates[index] = template.model_dump(mode="json")
                updated = True
                break

        if not updated:
            templates.append(template.model_dump(mode="json"))

        self._write_json(templates)
        return template

    def delete_template(self, template_id: str) -> bool:
        templates = self._read_json()
        remaining = []
        deleted = False
        image_path: str | None = None
        artifact_path: str | None = None

        for item in templates:
            if item.get("id") == template_id:
                deleted = True
                image_path = item.get("imagePath")
                artifact_data = item.get("paperFeatureArtifact")
                if isinstance(artifact_data, dict):
                    raw_artifact_path = artifact_data.get("artifactPath")
                    if isinstance(raw_artifact_path, str):
                        artifact_path = raw_artifact_path
                continue
            remaining.append(item)

        if not deleted:
            return False

        self._write_json(remaining)

        if image_path:
            target = self.data_dir.parent / image_path.removeprefix("/")
            if target.exists():
                target.unlink()

        if artifact_path:
            target = self.data_dir.parent / artifact_path.removeprefix("/")
            if target.exists():
                target.unlink()

        return True

    def next_template_id(self) -> str:
        return f"tpl_{uuid4().hex[:12]}"
