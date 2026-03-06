from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np
import pytesseract

from app.models.template_models import ZoneModel, ZoneType


@dataclass(frozen=True)
class OCRWord:
    id: int
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    block_num: int
    par_num: int
    line_num: int


def _normalize_text(value: str, zone_type: ZoneType) -> str:
    cleaned = " ".join(value.split())
    if zone_type == "number":
        return re.sub(r"[^0-9.,-]", "", cleaned)
    if zone_type == "date":
        return re.sub(r"[^0-9/.-]", "", cleaned)
    if zone_type == "alphanumeric":
        return re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return cleaned


def run_word_ocr(image: np.ndarray) -> tuple[list[OCRWord], str | None]:
    try:
        data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return [], "Tesseract executable not found"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return [], f"OCR failed: {exc}"

    words: list[OCRWord] = []
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue

        try:
            confidence_raw = float(data["conf"][index])
        except ValueError:
            continue

        if confidence_raw < 0:
            continue

        width = int(data["width"][index])
        height = int(data["height"][index])
        if width <= 0 or height <= 0:
            continue

        words.append(
            OCRWord(
                id=len(words),
                text=text,
                confidence=confidence_raw / 100.0,
                x=int(data["left"][index]),
                y=int(data["top"][index]),
                width=width,
                height=height,
                block_num=int(data["block_num"][index]),
                par_num=int(data["par_num"][index]),
                line_num=int(data["line_num"][index]),
            )
        )

    return words, None


def _intersection_area(
    ax: int,
    ay: int,
    aw: int,
    ah: int,
    bx: int,
    by: int,
    bw: int,
    bh: int,
) -> int:
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def extract_zone_text_from_words(
    *,
    zone: ZoneModel,
    words: list[OCRWord],
    min_word_overlap: float = 0.2,
    zone_padding: int = 4,
) -> tuple[str, float, str | None, list[int]]:
    zone_x = zone.x - zone_padding
    zone_y = zone.y - zone_padding
    zone_width = zone.width + (2 * zone_padding)
    zone_height = zone.height + (2 * zone_padding)

    matched: list[tuple[OCRWord, float]] = []
    for word in words:
        intersection = _intersection_area(
            zone_x,
            zone_y,
            zone_width,
            zone_height,
            word.x,
            word.y,
            word.width,
            word.height,
        )
        if intersection == 0:
            continue

        word_area = word.width * word.height
        if word_area <= 0:
            continue

        overlap_ratio = intersection / word_area
        center_x = word.x + (word.width / 2)
        center_y = word.y + (word.height / 2)
        center_in_zone = (
            zone_x <= center_x <= zone_x + zone_width and zone_y <= center_y <= zone_y + zone_height
        )

        if overlap_ratio >= min_word_overlap or center_in_zone:
            score = overlap_ratio + (0.25 if center_in_zone else 0.0)
            matched.append((word, score))

    if not matched:
        return "", 0.0, "No OCR words intersect zone", []

    matched.sort(key=lambda item: (item[0].block_num, item[0].par_num, item[0].line_num, item[0].x))

    ordered_words: list[str] = []
    last_line: tuple[int, int, int] | None = None
    weighted_conf_sum = 0.0
    weight_sum = 0.0

    for word, score in matched:
        current_line = (word.block_num, word.par_num, word.line_num)
        if last_line is not None and current_line != last_line:
            ordered_words.append("\n")
        ordered_words.append(word.text)
        last_line = current_line

        weight = max(score, 0.05)
        weighted_conf_sum += word.confidence * weight
        weight_sum += weight

    raw_text = " ".join(ordered_words).replace("\n ", "\n").strip()
    normalized = _normalize_text(raw_text, zone.type)
    confidence = weighted_conf_sum / weight_sum if weight_sum > 0 else 0.0

    warning = None
    if not normalized:
        warning = "OCR words matched but value is empty"
    elif confidence < 0.5:
        warning = "Low OCR confidence"

    matched_word_ids = [word.id for word, _ in matched]
    return normalized, confidence, warning, matched_word_ids
