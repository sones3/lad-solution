from __future__ import annotations

import numpy as np

from app.models.template_models import ZoneModel


def extract_zone(image: np.ndarray, zone: ZoneModel) -> np.ndarray:
    image_height, image_width = image.shape[:2]

    x = max(0, min(zone.x, image_width - 1))
    y = max(0, min(zone.y, image_height - 1))
    max_width = image_width - x
    max_height = image_height - y
    width = max(1, min(zone.width, max_width))
    height = max(1, min(zone.height, max_height))

    return image[y : y + height, x : x + width]
