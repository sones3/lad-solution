from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class PaperTemplateFeatures:
    keypoints: list[cv2.KeyPoint]
    descriptors: np.ndarray
    stability: np.ndarray


def save_paper_template_features(
    features_dir: Path,
    *,
    template_id: str,
    keypoints: list[cv2.KeyPoint],
    descriptors: np.ndarray,
    stability: np.ndarray,
) -> str:
    features_dir.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{template_id}-paper-orb.npz"
    artifact_path = features_dir / artifact_name
    np.savez_compressed(
        artifact_path,
        keypoints=_serialize_keypoints(keypoints),
        descriptors=np.asarray(descriptors),
        stability=np.asarray(stability, dtype=np.int32),
    )
    return f"/data/template_features/{artifact_name}"


def load_paper_template_features(artifact_path: Path) -> PaperTemplateFeatures:
    with np.load(artifact_path, allow_pickle=False) as payload:
        serialized_keypoints = np.asarray(payload["keypoints"], dtype=np.float32)
        descriptors = np.asarray(payload["descriptors"])
        stability = np.asarray(payload["stability"], dtype=np.int32)

    return PaperTemplateFeatures(
        keypoints=_deserialize_keypoints(serialized_keypoints),
        descriptors=descriptors,
        stability=stability,
    )


def _serialize_keypoints(keypoints: list[cv2.KeyPoint]) -> np.ndarray:
    if not keypoints:
        return np.zeros((0, 7), dtype=np.float32)

    return np.asarray(
        [
            [
                float(keypoint.pt[0]),
                float(keypoint.pt[1]),
                float(keypoint.size),
                float(keypoint.angle),
                float(keypoint.response),
                float(keypoint.octave),
                float(keypoint.class_id),
            ]
            for keypoint in keypoints
        ],
        dtype=np.float32,
    )


def _deserialize_keypoints(serialized_keypoints: np.ndarray) -> list[cv2.KeyPoint]:
    keypoints: list[cv2.KeyPoint] = []
    for x, y, size, angle, response, octave, class_id in serialized_keypoints:
        keypoints.append(
            cv2.KeyPoint(
                x=float(x),
                y=float(y),
                size=max(float(size), 1.0),
                angle=float(angle),
                response=float(response),
                octave=int(round(float(octave))),
                class_id=int(round(float(class_id))),
            )
        )
    return keypoints
