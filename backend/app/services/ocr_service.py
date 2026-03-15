from __future__ import annotations

from dataclasses import dataclass, replace
import os
import re
from typing import Any, Literal

import cv2
import numpy as np
import pytesseract

from app.models.template_models import ZoneModel, ZoneType

OCREngine = Literal["tesseract", "paddleocr"]
PADDLE_MAX_LONG_SIDE = 1600

# os.environ.setdefault("OMP_THREAD_LIMIT", "1")


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


@dataclass(frozen=True)
class OCRTextConfig:
    lang: str = "fra+eng"
    psm: int = 6
    oem: int = 1
    timeout: int = 12


def _normalize_text(value: str, zone_type: ZoneType) -> str:
    cleaned = " ".join(value.split())
    if zone_type == "number":
        return re.sub(r"[^0-9.,-]", "", cleaned)
    if zone_type == "date":
        return re.sub(r"[^0-9/.-]", "", cleaned)
    if zone_type == "alphanumeric":
        return re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return cleaned


def _run_tesseract_word_ocr(image: np.ndarray) -> tuple[list[OCRWord], str | None]:
    try:
        data = pytesseract.image_to_data(image, config="--psm 6", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return [], "Tesseract executable not found"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return [], f"Tesseract OCR failed: {exc}"

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


def run_text_ocr(image: np.ndarray, *, config: OCRTextConfig | None = None) -> tuple[str, str | None]:
    selected_config = config or OCRTextConfig()
    tesseract_config = (
        f"--oem {selected_config.oem} --psm {selected_config.psm} "
        "-c load_system_dawg=0 -c load_freq_dawg=0"
    )

    try:
        return (
            pytesseract.image_to_string(
                image,
                lang=selected_config.lang,
                config=tesseract_config,
                timeout=selected_config.timeout,
            ),
            None,
        )
    except pytesseract.TesseractNotFoundError:
        return "", "Tesseract executable not found"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return "", f"Tesseract OCR failed: {exc}"


def _normalize_paddle_box(box: Any) -> tuple[int, int, int, int] | None:
    array = np.array(box)
    if array.size == 0:
        return None

    if array.ndim == 1 and array.shape[0] >= 4:
        x1, y1, x2, y2 = array[:4].astype(float).tolist()
        left = int(round(min(x1, x2)))
        top = int(round(min(y1, y2)))
        width = int(round(abs(x2 - x1)))
        height = int(round(abs(y2 - y1)))
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height

    if array.ndim == 2 and array.shape[1] >= 2:
        xs = array[:, 0].astype(float)
        ys = array[:, 1].astype(float)
        left = int(round(float(xs.min())))
        top = int(round(float(ys.min())))
        right = int(round(float(xs.max())))
        bottom = int(round(float(ys.max())))
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height

    return None


def _extract_paddle_payload(first_result: Any) -> dict[str, Any]:
    payload: Any
    if isinstance(first_result, dict):
        payload = first_result
    elif hasattr(first_result, "to_dict"):
        payload = first_result.to_dict()
    elif hasattr(first_result, "dict"):
        payload = first_result.dict()
    else:
        payload = {}

    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        return payload["res"]
    if isinstance(payload, dict):
        return payload
    return {}


def _coerce_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _resize_for_paddle(image: np.ndarray) -> tuple[np.ndarray, float, float]:
    height, width = image.shape[:2]
    long_side = max(height, width)
    if long_side <= PADDLE_MAX_LONG_SIDE:
        return image, 1.0, 1.0

    scale = PADDLE_MAX_LONG_SIDE / float(long_side)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    scale_x = width / float(new_width)
    scale_y = height / float(new_height)
    return resized, scale_x, scale_y


def _assign_line_numbers(words: list[OCRWord]) -> list[OCRWord]:
    if not words:
        return words

    sorted_words = sorted(words, key=lambda word: (word.y, word.x))
    heights = np.array([word.height for word in words], dtype=np.float32)
    median_height = float(np.median(heights)) if heights.size else 12.0
    line_threshold = max(8.0, median_height * 0.6)

    line_centers: list[float] = []
    line_by_word_id: dict[int, int] = {}

    for word in sorted_words:
        center_y = word.y + (word.height / 2)

        nearest_line: int | None = None
        nearest_distance = float("inf")
        for line_index, line_center in enumerate(line_centers):
            distance = abs(center_y - line_center)
            if distance <= line_threshold and distance < nearest_distance:
                nearest_line = line_index
                nearest_distance = distance

        if nearest_line is None:
            nearest_line = len(line_centers)
            line_centers.append(center_y)
        else:
            line_centers[nearest_line] = (line_centers[nearest_line] + center_y) / 2.0

        line_by_word_id[word.id] = nearest_line

    return [
        replace(word, block_num=0, par_num=0, line_num=line_by_word_id.get(word.id, 0))
        for word in words
    ]


def _run_paddle_word_ocr(
    image: np.ndarray,
    paddle_ocr: Any | None,
    paddle_init_error: str | None,
) -> tuple[list[OCRWord], str | None]:
    if paddle_ocr is None:
        if paddle_init_error:
            return [], paddle_init_error
        return [], "PaddleOCR is not initialized"

    resized_image, scale_x, scale_y = _resize_for_paddle(image)

    try:
        results = paddle_ocr.predict(resized_image)
    except Exception as exc:  # pragma: no cover - runtime dependency and model errors
        message = str(exc)
        if "ConvertPirAttribute2RuntimeAttribute" in message:
            return (
                [],
                "PaddleOCR failed due to a Paddle oneDNN/PIR runtime issue. "
                "Use PaddlePaddle < 3.3 and keep enable_mkldnn disabled.",
            )
        return [], f"PaddleOCR failed: {message}"

    if not results:
        return [], None

    payload = _extract_paddle_payload(results[0])
    rec_texts = _coerce_sequence(payload.get("rec_texts"))
    rec_scores = _coerce_sequence(payload.get("rec_scores"))
    rec_boxes = _coerce_sequence(payload.get("rec_boxes"))
    count = min(len(rec_texts), len(rec_scores), len(rec_boxes))

    words: list[OCRWord] = []
    for index in range(count):
        text = str(rec_texts[index]).strip()
        if not text:
            continue

        try:
            confidence_raw = float(rec_scores[index])
        except (TypeError, ValueError):
            continue

        bbox = _normalize_paddle_box(rec_boxes[index])
        if bbox is None:
            continue

        left, top, width, height = bbox
        left = int(round(left * scale_x))
        top = int(round(top * scale_y))
        width = int(round(width * scale_x))
        height = int(round(height * scale_y))

        if width <= 0 or height <= 0:
            continue

        confidence = confidence_raw / 100.0 if confidence_raw > 1.0 else confidence_raw
        confidence = max(0.0, min(1.0, confidence))

        words.append(
            OCRWord(
                id=len(words),
                text=text,
                confidence=confidence,
                x=left,
                y=top,
                width=width,
                height=height,
                block_num=0,
                par_num=0,
                line_num=0,
            )
        )

    words = _assign_line_numbers(words)
    return words, None


def run_word_ocr(
    image: np.ndarray,
    *,
    engine: OCREngine,
    paddle_ocr: Any | None = None,
    paddle_init_error: str | None = None,
) -> tuple[list[OCRWord], str | None]:
    if engine == "tesseract":
        return _run_tesseract_word_ocr(image)
    if engine == "paddleocr":
        return _run_paddle_word_ocr(image, paddle_ocr=paddle_ocr, paddle_init_error=paddle_init_error)
    return [], f"Unsupported OCR engine: {engine}"


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
