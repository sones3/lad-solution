from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

import cv2
import numpy as np

from app.models.template_models import IgnoreRegionModel
from app.services.synthetic_augmentations import iter_synthetic_views

PAPER_DETECTOR = "orb"
PAPER_EPSILON = 5
PAPER_SYNTHESIZED_IMAGE_COUNT = 1000
PAPER_MAX_KEYPOINTS = 300
PAPER_MAX_BUILD_DIMENSION = 1400
FEATURE_RATIO_TEST = 0.75


@dataclass(frozen=True)
class StableTemplateFeatures:
    keypoints: list[cv2.KeyPoint]
    descriptors: np.ndarray
    stability: np.ndarray


@dataclass(frozen=True)
class PreparedPaperTemplate:
    image: np.ndarray
    ignore_regions: list[IgnoreRegionModel]
    scale_factor: float


def build_stable_paper_template_features(
    template_image: np.ndarray,
    *,
    ignore_regions: list[IgnoreRegionModel],
    max_keypoints: int = PAPER_MAX_KEYPOINTS,
    epsilon: int = PAPER_EPSILON,
    synthesized_image_count: int = PAPER_SYNTHESIZED_IMAGE_COUNT,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> StableTemplateFeatures:
    if progress_callback is not None:
        progress_callback("detect_template_keypoints", 0, synthesized_image_count)

    detector = cast(Any, create_paper_detector())
    template_gray = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY)
    full_mask = np.full(template_gray.shape, 255, dtype=np.uint8)
    keypoints, descriptors = detector.detectAndCompute(template_gray, full_mask)

    if descriptors is None or not keypoints:
        raise RuntimeError("Unable to detect ORB keypoints on the template image")

    filtered_pairs = [
        (keypoint, descriptor)
        for keypoint, descriptor in zip(keypoints, descriptors, strict=False)
        if not _is_in_ignored_region(keypoint, ignore_regions)
    ]
    if not filtered_pairs:
        raise RuntimeError("No ORB keypoints remain after masking varying fields")

    filtered_keypoints = [keypoint for keypoint, _ in filtered_pairs]
    filtered_descriptors = np.asarray([descriptor for _, descriptor in filtered_pairs], dtype=np.uint8)
    template_points = np.asarray([keypoint.pt for keypoint in filtered_keypoints], dtype=np.float32).reshape(-1, 1, 2)
    stability = np.zeros(len(filtered_keypoints), dtype=np.int32)
    if progress_callback is not None:
        progress_callback("score_stability", 0, synthesized_image_count)

    progress_checkpoints = {
        1,
        2,
        5,
        10,
        max(1, synthesized_image_count // 20),
    }
    progress_interval = max(1, synthesized_image_count // 20)
    for index, synthetic_view in enumerate(
        iter_synthetic_views(template_image, count=synthesized_image_count),
        start=1,
    ):
        if progress_callback is not None and (index in progress_checkpoints or index % progress_interval == 0):
            progress_callback("generate_synthetic_view", index, synthesized_image_count)

        synthetic_gray = cv2.cvtColor(synthetic_view.image, cv2.COLOR_BGR2GRAY)
        synthetic_mask = np.full(synthetic_gray.shape, 255, dtype=np.uint8)
        synthetic_keypoints, _ = detector.detectAndCompute(synthetic_gray, synthetic_mask)
        if not synthetic_keypoints:
            if progress_callback is not None and (
                index == synthesized_image_count or index in progress_checkpoints or index % progress_interval == 0
            ):
                progress_callback("score_stability", index, synthesized_image_count)
            continue

        coverage = _build_keypoint_coverage_mask(
            image_shape=synthetic_gray.shape,
            keypoints=synthetic_keypoints,
            epsilon=epsilon,
        )
        projected_points = cv2.perspectiveTransform(template_points, synthetic_view.homography).reshape(-1, 2)
        x_coords = np.rint(projected_points[:, 0]).astype(np.int32)
        y_coords = np.rint(projected_points[:, 1]).astype(np.int32)
        in_bounds = (
            (x_coords >= 0)
            & (x_coords < synthetic_gray.shape[1])
            & (y_coords >= 0)
            & (y_coords < synthetic_gray.shape[0])
        )
        if np.any(in_bounds):
            stability[in_bounds] += (coverage[y_coords[in_bounds], x_coords[in_bounds]] > 0).astype(np.int32)
        if progress_callback is not None and (
            index == synthesized_image_count or index in progress_checkpoints or index % progress_interval == 0
        ):
            progress_callback("score_stability", index, synthesized_image_count)

    ranked_indices = np.argsort(-stability, kind="stable")[:max_keypoints]
    selected_keypoints = [filtered_keypoints[index] for index in ranked_indices]
    selected_descriptors = filtered_descriptors[ranked_indices]
    selected_stability = stability[ranked_indices]

    if not selected_keypoints or selected_descriptors.size == 0:
        raise RuntimeError("Failed to select stable ORB keypoints for the paper method")

    if progress_callback is not None:
        progress_callback("select_top_keypoints", synthesized_image_count, synthesized_image_count)

    return StableTemplateFeatures(
        keypoints=selected_keypoints,
        descriptors=np.asarray(selected_descriptors, dtype=np.uint8),
        stability=np.asarray(selected_stability, dtype=np.int32),
    )


def prepare_paper_template_inputs(
    template_image: np.ndarray,
    ignore_regions: list[IgnoreRegionModel],
    *,
    max_dimension: int = PAPER_MAX_BUILD_DIMENSION,
) -> PreparedPaperTemplate:
    height, width = template_image.shape[:2]
    longest_side = max(height, width)
    if longest_side <= max_dimension:
        return PreparedPaperTemplate(
            image=template_image,
            ignore_regions=ignore_regions,
            scale_factor=1.0,
        )

    scale_factor = max_dimension / float(longest_side)
    resized_width = max(1, int(round(width * scale_factor)))
    resized_height = max(1, int(round(height * scale_factor)))
    resized_image = cv2.resize(template_image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    resized_regions = [
        IgnoreRegionModel(
            id=region.id,
            name=region.name,
            x=max(0, int(round(region.x * scale_factor))),
            y=max(0, int(round(region.y * scale_factor))),
            width=max(10, int(round(region.width * scale_factor))),
            height=max(10, int(round(region.height * scale_factor))),
        )
        for region in ignore_regions
    ]
    return PreparedPaperTemplate(
        image=resized_image,
        ignore_regions=resized_regions,
        scale_factor=scale_factor,
    )


def create_paper_detector() -> cv2.Feature2D:
    return cv2.ORB_create(  # pyright: ignore[reportAttributeAccessIssue]
        nfeatures=3000,
        scaleFactor=1.2,
        nlevels=8,
        fastThreshold=20,
    )


def _is_in_ignored_region(keypoint: cv2.KeyPoint, ignore_regions: list[IgnoreRegionModel]) -> bool:
    x_coord, y_coord = keypoint.pt
    for region in ignore_regions:
        if region.x <= x_coord <= region.x + region.width and region.y <= y_coord <= region.y + region.height:
            return True
    return False


def _build_keypoint_coverage_mask(
    *,
    image_shape: tuple[int, int],
    keypoints: list[cv2.KeyPoint],
    epsilon: int,
) -> np.ndarray:
    mask = np.zeros(image_shape, dtype=np.uint8)
    height, width = image_shape
    for keypoint in keypoints:
        x_coord = int(round(keypoint.pt[0]))
        y_coord = int(round(keypoint.pt[1]))
        if 0 <= x_coord < width and 0 <= y_coord < height:
            mask[y_coord, x_coord] = 255
    kernel_size = (epsilon * 2) + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    return cv2.dilate(mask, kernel)
