from __future__ import annotations

import cv2
import numpy as np

WOLF_PARAMS = {"window": 95, "k": 0.1}


def wolf_binarize(image_bgr: np.ndarray) -> np.ndarray:
    try:
        import doxapy
    except ImportError as exc:  # pragma: no cover - dependency issue only at runtime
        raise RuntimeError("doxapy is not installed. Install it to use Wolf binarization.") from exc

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    gray_u8 = np.ascontiguousarray(gray.astype(np.uint8))

    wolf = doxapy.Binarization(doxapy.Binarization.Algorithms.WOLF)  # type: ignore[attr-defined]
    wolf.initialize(gray_u8)

    binary = np.empty(gray_u8.shape, dtype=gray_u8.dtype)
    wolf.to_binary(binary, WOLF_PARAMS)
    return binary


def to_bgr(gray_or_bgr: np.ndarray) -> np.ndarray:
    if len(gray_or_bgr.shape) == 2:
        return cv2.cvtColor(gray_or_bgr, cv2.COLOR_GRAY2BGR)
    return gray_or_bgr
