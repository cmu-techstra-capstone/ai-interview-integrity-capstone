"""Aditi detection-model integration boundary.

This package defines the adapter surface for a future compatible detection model.
It does **not** ship a production detector, scoring formula, thresholds, or calibrated
confidence. Mock detectors exist in tests only.
"""

from .boundary import (
    DetectionInference,
    DetectionModel,
    DetectionStatus,
    ModelUnavailableDetector,
    run_detection,
)

__all__ = [
    "DetectionInference",
    "DetectionModel",
    "DetectionStatus",
    "ModelUnavailableDetector",
    "run_detection",
]
