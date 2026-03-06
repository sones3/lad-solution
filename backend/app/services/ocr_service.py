from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract

from app.models.template_models import ZoneType


def _normalize_text(value: str, zone_type: ZoneType) -> str:
    cleaned = " ".join(value.split())
    if zone_type == "number":
        return re.sub(r"[^0-9.,-]", "", cleaned)
    if zone_type == "date":
        return re.sub(r"[^0-9/.-]", "", cleaned)
    if zone_type == "alphanumeric":
        return re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return cleaned


def run_ocr(roi: np.ndarray, zone_type: ZoneType) -> tuple[str, float, str | None]:
    if roi.size == 0:
        return "", 0.0, "Empty ROI"

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    processed = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )

    try:
        config = "--psm 6"
        raw_text = pytesseract.image_to_string(processed, config=config)
        data = pytesseract.image_to_data(processed, config=config, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return "", 0.0, "Tesseract executable not found"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return "", 0.0, f"OCR failed: {exc}"

    confidences = []
    for conf in data.get("conf", []):
        try:
            parsed = float(conf)
        except ValueError:
            continue
        if parsed >= 0:
            confidences.append(parsed)

    confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    normalized = _normalize_text(raw_text, zone_type)
    warning = None
    if not normalized:
        warning = "OCR returned empty text"
    elif confidence < 0.5:
        warning = "Low OCR confidence"

    return normalized, confidence, warning
