from __future__ import annotations

import multiprocessing
from typing import Any

_paddle_ocr: Any | None = None
_paddle_init_error: str | None = None


def initialize_paddle_ocr() -> None:
    global _paddle_ocr
    global _paddle_init_error

    if _paddle_ocr is not None or _paddle_init_error is not None:
        return

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        _paddle_init_error = f"PaddleOCR import failed: {exc}"
        return

    try:
        _paddle_ocr = PaddleOCR(
            # cpu_threads=multiprocessing.cpu_count(),
            # enable_mkldnn=True,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
        )
    except Exception as exc:  # pragma: no cover - depends on runtime environment
        _paddle_init_error = f"PaddleOCR initialization failed: {exc}"
        _paddle_ocr = None


def get_paddle_ocr() -> tuple[Any | None, str | None]:
    return _paddle_ocr, _paddle_init_error
