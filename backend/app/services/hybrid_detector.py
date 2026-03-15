from __future__ import annotations

# pyright: reportMissingImports=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false

from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

try:
    import imagehash
    from PIL import Image
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing
    imagehash = None
    Image = None


@dataclass(frozen=True)
class AnchorRegion:
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    weight: float
    critical: bool = False


ANCHOR_REGIONS: tuple[AnchorRegion, ...] = (
    AnchorRegion("header_left", 0.00, 0.00, 0.35, 0.20, 0.24, True),
    AnchorRegion("header_center", 0.20, 0.04, 0.80, 0.22, 0.28, True),
    AnchorRegion("header_right", 0.65, 0.00, 1.00, 0.22, 0.18, True),
    AnchorRegion("body_left", 0.06, 0.25, 0.42, 0.58, 0.10, False),
    AnchorRegion("footer_band", 0.00, 0.72, 1.00, 0.95, 0.20, True),
)


@dataclass
class PreparedHybridTemplate:
    region_signatures: dict[str, dict[str, object]]


@dataclass
class HybridDetectionResult:
    visual_score: float
    orb_score: float
    final_score: float
    critical_score: float
    warnings: list[str]


def prepare_hybrid_template(template_image: np.ndarray) -> PreparedHybridTemplate:
    _ensure_dependencies()
    gray = cv2.cvtColor(template_image, cv2.COLOR_BGR2GRAY)
    processed = _preprocess(gray)
    return PreparedHybridTemplate(
        region_signatures={
            region.name: _compute_region_signature(_extract_region(processed, region)) for region in ANCHOR_REGIONS
        }
    )


def detect_with_hybrid(
    prepared_template: PreparedHybridTemplate,
    page_image: np.ndarray,
    *,
    orb_confirmation: float,
    threshold: float,
    evaluate_orb_gate: bool = True,
) -> HybridDetectionResult:
    _ensure_dependencies()

    gray = cv2.cvtColor(page_image, cv2.COLOR_BGR2GRAY)
    processed = _preprocess(gray)

    weighted_score = 0.0
    total_weight = 0.0
    critical_score = 0.0
    critical_weight = 0.0
    warnings: list[str] = []

    for region in ANCHOR_REGIONS:
        signature = prepared_template.region_signatures.get(region.name)
        if signature is None:
            continue
        score = _compare_region(_extract_region(processed, region), signature)
        weighted_score += score * region.weight
        total_weight += region.weight
        if region.critical:
            critical_score += score * region.weight
            critical_weight += region.weight

    visual_score = weighted_score / total_weight if total_weight > 0 else 0.0
    critical_visual_score = critical_score / critical_weight if critical_weight > 0 else visual_score
    final_score = (visual_score * 0.45) + (orb_confirmation * 0.55)

    anchor_gate = max(0.30, threshold - 0.15)
    critical_gate = max(0.33, threshold - 0.10)
    orb_gate = max(0.18, threshold - 0.25)

    if visual_score < anchor_gate:
        warnings.append(f"Anchor score {visual_score:.3f} below gate {anchor_gate:.3f}")
    if critical_visual_score < critical_gate:
        warnings.append(f"Critical anchor score {critical_visual_score:.3f} below gate {critical_gate:.3f}")
    if evaluate_orb_gate and orb_confirmation < orb_gate:
        warnings.append(f"ORB confirmation {orb_confirmation:.3f} below gate {orb_gate:.3f}")

    return HybridDetectionResult(
        visual_score=visual_score,
        orb_score=orb_confirmation,
        final_score=final_score,
        critical_score=critical_visual_score,
        warnings=warnings,
    )


def _ensure_dependencies() -> None:
    if imagehash is None or Image is None:
        raise RuntimeError("imagehash and Pillow are required for hybrid detection")


def _preprocess(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.GaussianBlur(enhanced, (3, 3), 0)


def _extract_region(gray: np.ndarray, region: AnchorRegion) -> np.ndarray:
    height, width = gray.shape[:2]
    x0 = int(width * region.x0)
    y0 = int(height * region.y0)
    x1 = int(width * region.x1)
    y1 = int(height * region.y1)
    cropped = gray[y0:y1, x0:x1]
    if cropped.size == 0:
        return gray
    return cropped


def _compute_region_signature(region: np.ndarray) -> dict[str, object]:
    if Image is None or imagehash is None:
        raise RuntimeError("imagehash and Pillow are required for hybrid detection")

    image_class = Image
    imagehash_module = imagehash
    image = image_class.fromarray(region).resize((384, 384), image_class.Resampling.LANCZOS)
    histogram = cv2.calcHist([region], [0], None, [256], [0, 256]).flatten().astype(np.float32)
    edges = cv2.Canny(region, 80, 180)
    edge_density = float(np.mean(edges > 0))
    return {
        "hashes": {
            "phash": str(imagehash_module.phash(image, hash_size=16)),
            "dhash": str(imagehash_module.dhash(image, hash_size=8)),
            "whash": str(imagehash_module.whash(image, hash_size=8)),
        },
        "histogram": histogram,
        "edgeDensity": edge_density,
    }


def _compare_region(page_region: np.ndarray, template_region: dict[str, object]) -> float:
    if Image is None or imagehash is None:
        raise RuntimeError("imagehash and Pillow are required for hybrid detection")

    image_class = Image
    imagehash_module = imagehash
    image = image_class.fromarray(page_region).resize((384, 384), image_class.Resampling.LANCZOS)
    template_hashes = cast(dict[str, str], template_region.get("hashes", {}))
    template_histogram = np.asarray(
        cast(list[float] | np.ndarray, template_region.get("histogram", [])),
        dtype=np.float32,
    )
    template_edge_density = float(cast(float | int, template_region.get("edgeDensity", 0.0)))

    hash_scores: list[tuple[float, float]] = []
    for key, factory, denominator, weight in (
        ("phash", lambda img: imagehash_module.phash(img, hash_size=16), 256.0, 0.45),
        ("dhash", lambda img: imagehash_module.dhash(img, hash_size=8), 64.0, 0.25),
        ("whash", lambda img: imagehash_module.whash(img, hash_size=8), 64.0, 0.30),
    ):
        template_hash = template_hashes.get(key)
        if not isinstance(template_hash, str):
            continue
        similarity = 1.0 - ((imagehash_module.hex_to_hash(template_hash) - factory(image)) / denominator)
        hash_scores.append((max(0.0, min(1.0, similarity)), weight))

    hash_score = 0.0
    if hash_scores:
        total_weight = sum(weight for _, weight in hash_scores)
        hash_score = sum(score * weight for score, weight in hash_scores) / total_weight

    histogram_score = 0.0
    if template_histogram.size > 0:
        page_histogram = cv2.calcHist([page_region], [0], None, [256], [0, 256]).flatten().astype(np.float32)
        page_histogram /= page_histogram.sum() + 1e-10
        normalized_template_histogram = template_histogram / (template_histogram.sum() + 1e-10)
        histogram_score = max(
            0.0,
            float(cv2.compareHist(page_histogram, normalized_template_histogram, cv2.HISTCMP_CORREL)),
        )

    page_edge_density = float(np.mean(cv2.Canny(page_region, 80, 180) > 0))
    edge_delta = abs(page_edge_density - template_edge_density)
    edge_score = max(0.0, 1.0 - min(edge_delta / 0.15, 1.0))

    return (hash_score * 0.60) + (histogram_score * 0.25) + (edge_score * 0.15)
