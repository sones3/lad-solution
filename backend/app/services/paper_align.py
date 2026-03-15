from __future__ import annotations

import cv2
import numpy as np

from app.services.orb_align import AlignmentResult
from app.services.template_feature_stability import FEATURE_RATIO_TEST, create_paper_detector
from app.services.template_feature_store import PaperTemplateFeatures


def align_document_with_paper_features(
    *,
    template_image: np.ndarray,
    template_features: PaperTemplateFeatures,
    input_image: np.ndarray,
    warp: bool = False,
) -> AlignmentResult:
    warnings: list[str] = []
    detector = create_paper_detector()
    input_gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)
    input_keypoints, input_descriptors = detector.detectAndCompute(input_gray, None)  # pyright: ignore[reportAttributeAccessIssue]

    if input_descriptors is None or not input_keypoints:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=0,
            warnings=warnings,
            error="Unable to detect enough paper-method ORB features",
        )

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw_matches = matcher.knnMatch(template_features.descriptors, np.asarray(input_descriptors, dtype=np.uint8), k=2)

    good_matches: list[cv2.DMatch] = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        first, second = pair
        if first.distance < FEATURE_RATIO_TEST * second.distance:
            good_matches.append(first)

    if len(good_matches) < 20:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=len(good_matches),
            warnings=warnings,
            error=f"Not enough good paper-method ORB matches ({len(good_matches)})",
        )

    src_points = np.asarray(
        [
            (float(input_keypoints[match.trainIdx].pt[0]), float(input_keypoints[match.trainIdx].pt[1]))
            for match in good_matches
        ],
        dtype=np.float32,
    ).reshape(-1, 1, 2)
    dst_points = np.asarray(
        [
            (float(template_features.keypoints[match.queryIdx].pt[0]), float(template_features.keypoints[match.queryIdx].pt[1]))
            for match in good_matches
        ],
        dtype=np.float32,
    ).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 4.0)
    if homography is None or mask is None:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=len(good_matches),
            warnings=warnings,
            error="Failed to compute homography for paper method",
        )

    inlier_ratio = float(mask.ravel().mean())
    if inlier_ratio < 0.35:
        warnings.append(f"Low paper-method alignment confidence: inlier ratio {inlier_ratio:.3f}")

    aligned_image: np.ndarray | None = None
    if warp:
        height, width = template_image.shape[:2]
        aligned_image = cv2.warpPerspective(input_image, homography, (width, height))

    return AlignmentResult(
        success=True,
        aligned_image=aligned_image,
        inlier_ratio=inlier_ratio,
        matches_used=len(good_matches),
        warnings=warnings,
    )
