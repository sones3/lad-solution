from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class AlignmentResult:
    success: bool
    aligned_image: np.ndarray | None
    inlier_ratio: float
    matches_used: int
    warnings: list[str]
    error: str | None = None


def align_document_to_template(template_image: np.ndarray, input_image: np.ndarray) -> AlignmentResult:
    warnings: list[str] = []
    orb = cv2.ORB_create(nfeatures=3000, scaleFactor=1.2, nlevels=8, fastThreshold=20)

    template_gray = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY)
    input_gray = cv2.cvtColor(input_image, cv2.COLOR_BGR2GRAY)

    kp_template, des_template = orb.detectAndCompute(template_gray, None)
    kp_input, des_input = orb.detectAndCompute(input_gray, None)

    if des_template is None or des_input is None:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=0,
            warnings=warnings,
            error="Unable to detect enough features",
        )

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw_matches = matcher.knnMatch(des_template, des_input, k=2)

    good_matches = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        first, second = pair
        if first.distance < 0.75 * second.distance:
            good_matches.append(first)

    if len(good_matches) < 20:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=len(good_matches),
            warnings=warnings,
            error=f"Not enough good matches ({len(good_matches)})",
        )

    src_points = np.float32([kp_input[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_points = np.float32([kp_template[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 4.0)
    if homography is None or mask is None:
        return AlignmentResult(
            success=False,
            aligned_image=None,
            inlier_ratio=0.0,
            matches_used=len(good_matches),
            warnings=warnings,
            error="Failed to compute homography",
        )

    inlier_ratio = float(mask.ravel().mean())
    if inlier_ratio < 0.35:
        warnings.append(f"Low alignment confidence: inlier ratio {inlier_ratio:.3f}")

    height, width = template_image.shape[:2]
    aligned = cv2.warpPerspective(input_image, homography, (width, height))

    return AlignmentResult(
        success=True,
        aligned_image=aligned,
        inlier_ratio=inlier_ratio,
        matches_used=len(good_matches),
        warnings=warnings,
    )
