from __future__ import annotations

# pyright: reportMissingImports=false

from collections.abc import Iterator
import threading

import cv2
import numpy as np

try:
    import fitz  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing
    fitz = None


THREAD_LOCAL = threading.local()


def render_pdf_pages(pdf_bytes: bytes, *, dpi: int = 144) -> Iterator[tuple[int, np.ndarray]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed; PDF rendering is unavailable")

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # pragma: no cover - depends on parser internals
        raise RuntimeError("Unable to open PDF") from exc

    with document:
        for index, page in enumerate(document, start=1):
            yield index, _pixmap_to_bgr(page, dpi=dpi)


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed; PDF rendering is unavailable")

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            return len(document)
    except Exception as exc:  # pragma: no cover - depends on parser internals
        raise RuntimeError("Unable to open PDF") from exc


def render_pdf_page(pdf_bytes: bytes, *, page_number: int, dpi: int = 144) -> np.ndarray:
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed; PDF rendering is unavailable")

    document = _get_thread_pdf_document(pdf_bytes)
    try:
        page = document[page_number - 1]
    except Exception as exc:  # pragma: no cover - bounds depend on caller/runtime document state
        raise RuntimeError(f"Unable to render page {page_number}") from exc
    return _pixmap_to_bgr(page, dpi=dpi)


def _get_thread_pdf_document(pdf_bytes: bytes) -> fitz.Document:
    cache = getattr(THREAD_LOCAL, "pdf_cache", None)
    if cache is None:
        cache = {}
        THREAD_LOCAL.pdf_cache = cache

    key = (id(pdf_bytes), len(pdf_bytes))
    if key not in cache:
        try:
            cache[key] = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:  # pragma: no cover - depends on parser internals
            raise RuntimeError("Unable to open PDF") from exc
    return cache[key]


def _pixmap_to_bgr(page: fitz.Page, *, dpi: int) -> np.ndarray:
    scale = dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
    rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
    return cv2.cvtColor(rgb.copy(), cv2.COLOR_RGB2BGR)
