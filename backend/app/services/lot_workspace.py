from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re


LOT_ROOT_DIR = Path("/home/sones/lad-sep-stell")
LOT_NAME_PATTERN = re.compile(r"^VN LOT (\d+)$")
LOT_CONFIG_FILE = ".lad-config.json"
WORKBOOK_SUFFIX = ".reconciliation.xlsm"


@dataclass(frozen=True)
class LotWorkspaceConfig:
    template_id: str | None = None
    paper_threshold: float | None = None


@dataclass(frozen=True)
class LotWorkspace:
    name: str
    lot_number: int
    path: Path
    pdf_path: Path
    csv_path: Path
    sep_dir: Path
    workbook_path: Path
    config_path: Path
    pdf_present: bool
    csv_present: bool
    sep_present: bool
    workbook_present: bool
    status: str
    errors: list[str]
    last_modified: float
    config: LotWorkspaceConfig

    @property
    def outputs_exist(self) -> bool:
        return self.sep_present or self.workbook_present


def list_lot_workspaces(root_dir: Path = LOT_ROOT_DIR) -> list[LotWorkspace]:
    if not root_dir.exists() or not root_dir.is_dir():
        return []

    workspaces: list[LotWorkspace] = []
    for entry in root_dir.iterdir():
        if not entry.is_dir():
            continue
        match = LOT_NAME_PATTERN.fullmatch(entry.name)
        if match is None:
            continue
        workspaces.append(_build_workspace(entry, lot_number=int(match.group(1))))

    return sorted(workspaces, key=lambda workspace: workspace.lot_number, reverse=True)


def get_lot_workspace(name: str, root_dir: Path = LOT_ROOT_DIR) -> LotWorkspace | None:
    match = LOT_NAME_PATTERN.fullmatch(name)
    if match is None:
        return None

    lot_path = root_dir / name
    if not lot_path.is_dir():
        return None
    return _build_workspace(lot_path, lot_number=int(match.group(1)))


def save_lot_workspace_config(
    workspace: LotWorkspace, *, template_id: str, paper_threshold: float
) -> None:
    payload = {
        "templateId": template_id,
        "paperThreshold": paper_threshold,
    }
    workspace.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_workspace(path: Path, *, lot_number: int) -> LotWorkspace:
    name = path.name
    pdf_path = path / f"{name}.pdf"
    csv_path = path / f"{name}.csv"
    sep_dir = path / "sep"
    workbook_path = path / f"{name}{WORKBOOK_SUFFIX}"
    config_path = path / LOT_CONFIG_FILE

    root_pdfs = sorted(file for file in path.glob("*.pdf") if file.is_file())
    root_csvs = sorted(file for file in path.glob("*.csv") if file.is_file())

    errors: list[str] = []
    if not pdf_path.is_file():
        errors.append(f"Missing expected PDF: {pdf_path.name}")
    if not csv_path.is_file():
        errors.append(f"Missing expected CSV: {csv_path.name}")
    if len(root_pdfs) > 1 or any(file.name != pdf_path.name for file in root_pdfs):
        errors.append(f"Expected exactly one root PDF named {pdf_path.name}")
    if len(root_csvs) > 1 or any(file.name != csv_path.name for file in root_csvs):
        errors.append(f"Expected exactly one root CSV named {csv_path.name}")

    config = _load_config(config_path)
    return LotWorkspace(
        name=name,
        lot_number=lot_number,
        path=path,
        pdf_path=pdf_path,
        csv_path=csv_path,
        sep_dir=sep_dir,
        workbook_path=workbook_path,
        config_path=config_path,
        pdf_present=pdf_path.is_file(),
        csv_present=csv_path.is_file(),
        sep_present=sep_dir.is_dir(),
        workbook_present=workbook_path.is_file(),
        status="ready" if not errors else "incomplete",
        errors=errors,
        last_modified=_latest_mtime(path),
        config=config,
    )


def _load_config(config_path: Path) -> LotWorkspaceConfig:
    if not config_path.is_file():
        return LotWorkspaceConfig()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return LotWorkspaceConfig()

    template_id = payload.get("templateId")
    paper_threshold = payload.get("paperThreshold")
    try:
        threshold_value = None if paper_threshold is None else float(paper_threshold)
    except (TypeError, ValueError):
        threshold_value = None

    return LotWorkspaceConfig(
        template_id=template_id
        if isinstance(template_id, str) and template_id
        else None,
        paper_threshold=threshold_value,
    )


def _latest_mtime(path: Path) -> float:
    latest = path.stat().st_mtime
    for root, _, files in os.walk(path):
        root_path = Path(root)
        latest = max(latest, root_path.stat().st_mtime)
        for filename in files:
            try:
                latest = max(latest, (root_path / filename).stat().st_mtime)
            except OSError:
                continue
    return latest
