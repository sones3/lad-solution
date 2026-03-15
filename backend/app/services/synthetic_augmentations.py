from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class SyntheticView:
    image: np.ndarray
    homography: np.ndarray


def iter_synthetic_views(
    template_image: np.ndarray,
    *,
    count: int,
    seed: int | None = None,
) -> Iterator[SyntheticView]:
    rng = np.random.default_rng(seed)
    for _ in range(count):
        warped_image, homography = _apply_camera_distortion(template_image, rng)
        augmented_image = _apply_random_brightness(warped_image, rng)
        augmented_image = _apply_random_noise(augmented_image, rng)
        augmented_image = _apply_random_blur(augmented_image, rng)
        if rng.random() < 0.25:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            augmented_image = cv2.morphologyEx(augmented_image, cv2.MORPH_CLOSE, kernel)
        yield SyntheticView(image=augmented_image, homography=homography)


def _apply_camera_distortion(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    height, width = image.shape[:2]
    source_corners = np.asarray(
        [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]],
        dtype=np.float32,
    )

    focal_length = float(max(width, height) * rng.uniform(1.0, 1.6))
    base_distance = float(max(width, height) * rng.uniform(1.8, 2.8))
    shift_x = float(rng.uniform(-0.18, 0.18) * width)
    shift_y = float(rng.uniform(-0.18, 0.18) * height)
    roll, pitch, yaw = np.deg2rad(rng.uniform(-45.0, 45.0, size=3))
    rotation = _rotation_matrix(roll, pitch, yaw)

    destination_corners = np.asarray(
        [
            _project_corner(
                x=x - (width / 2.0),
                y=y - (height / 2.0),
                rotation=rotation,
                focal_length=focal_length,
                shift_x=shift_x,
                shift_y=shift_y,
                camera_distance=base_distance,
                canvas_width=width,
                canvas_height=height,
            )
            for x, y in source_corners
        ],
        dtype=np.float32,
    )

    homography = cv2.getPerspectiveTransform(source_corners, destination_corners)
    warped = cv2.warpPerspective(
        image,
        homography,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    return warped, homography


def _rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cos_x, sin_x = np.cos(roll), np.sin(roll)
    cos_y, sin_y = np.cos(pitch), np.sin(pitch)
    cos_z, sin_z = np.cos(yaw), np.sin(yaw)
    rotation_x = np.asarray([[1.0, 0.0, 0.0], [0.0, cos_x, -sin_x], [0.0, sin_x, cos_x]], dtype=np.float32)
    rotation_y = np.asarray([[cos_y, 0.0, sin_y], [0.0, 1.0, 0.0], [-sin_y, 0.0, cos_y]], dtype=np.float32)
    rotation_z = np.asarray([[cos_z, -sin_z, 0.0], [sin_z, cos_z, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    return rotation_z @ rotation_y @ rotation_x


def _project_corner(
    *,
    x: float,
    y: float,
    rotation: np.ndarray,
    focal_length: float,
    shift_x: float,
    shift_y: float,
    camera_distance: float,
    canvas_width: int,
    canvas_height: int,
) -> tuple[float, float]:
    point = rotation @ np.asarray([[x], [y], [0.0]], dtype=np.float32)
    z = float(point[2, 0] + camera_distance)
    if abs(z) < 1e-6:
        z = 1e-6
    projected_x = (focal_length * float(point[0, 0])) / z
    projected_y = (focal_length * float(point[1, 0])) / z
    return (
        projected_x + (canvas_width / 2.0) + shift_x,
        projected_y + (canvas_height / 2.0) + shift_y,
    )


def _apply_random_brightness(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    result = image.astype(np.float32)
    operations = [
        _apply_monotone_brightness_function,
        _apply_global_linear_brightness,
        _apply_smooth_line_brightness,
        _apply_half_plane_shadow,
    ]
    rng.shuffle(operations)
    for operation in operations[: rng.integers(1, len(operations) + 1)]:
        result = operation(result, rng)
    return np.clip(result, 0.0, 255.0).astype(np.uint8)


def _apply_monotone_brightness_function(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    control_points = np.sort(rng.uniform(0.0, 255.0, size=8))
    lookup_x = np.linspace(0.0, 255.0, num=8, dtype=np.float32)
    lookup_full = np.interp(np.arange(256, dtype=np.float32), lookup_x, control_points).astype(np.float32)
    return lookup_full[np.clip(image, 0, 255).astype(np.uint8)]


def _apply_global_linear_brightness(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    alpha = float(rng.uniform(0.65, 1.15))
    beta = float(rng.uniform(-55.0, 20.0))
    return (image * alpha) + beta


def _apply_smooth_line_brightness(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    height, width = image.shape[:2]
    angle = float(rng.uniform(0.0, 2.0 * np.pi))
    direction = np.asarray([np.cos(angle), np.sin(angle)], dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    projected = (xx * direction[0]) + (yy * direction[1])
    projected -= projected.min()
    projected /= projected.max() + 1e-6
    gradient = rng.uniform(-90.0, 90.0) * projected
    return image + gradient[..., None]


def _apply_half_plane_shadow(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    height, width = image.shape[:2]
    x1, y1 = rng.uniform(0, width), rng.uniform(0, height)
    x2, y2 = rng.uniform(0, width), rng.uniform(0, height)
    yy, xx = np.mgrid[0:height, 0:width]
    side = ((xx - x1) * (y2 - y1)) - ((yy - y1) * (x2 - x1))
    factor = float(rng.uniform(0.35, 0.8))
    result = image.copy()
    result[side >= 0] *= factor
    return result


def _apply_random_noise(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if rng.random() < 0.8:
        noise = rng.normal(loc=0.0, scale=rng.uniform(4.0, 18.0), size=image.shape)
        image = image.astype(np.float32) + noise.astype(np.float32)
    return np.clip(image, 0.0, 255.0).astype(np.uint8)


def _apply_random_blur(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    result = image
    if rng.random() < 0.7:
        sigma = float(rng.uniform(0.4, 2.4))
        result = cv2.GaussianBlur(result, (0, 0), sigmaX=sigma, sigmaY=sigma)
    if rng.random() < 0.5:
        result = cv2.filter2D(result, -1, _motion_kernel(rng))
    return result


def _motion_kernel(rng: np.random.Generator) -> np.ndarray:
    size = int(rng.integers(5, 17))
    if size % 2 == 0:
        size += 1
    kernel = np.zeros((size, size), dtype=np.float32)
    center = size // 2
    angle = float(rng.uniform(0.0, np.pi))
    direction = np.asarray([np.cos(angle), np.sin(angle)], dtype=np.float32)
    for offset in range(-center, center + 1):
        x = int(round(center + (offset * direction[0])))
        y = int(round(center + (offset * direction[1])))
        kernel[np.clip(y, 0, size - 1), np.clip(x, 0, size - 1)] = 1.0
    kernel /= kernel.sum() + 1e-6
    return kernel
