"""
Face Detection — MediaPipe Task API (v0.10+) wrapper.

Provides a lightweight, reusable face detector that:
  • Detects faces in a BGR frame (returns bounding boxes + confidence)
  • Crops the highest-confidence face region for downstream modules
  • Lazy-initialises the MediaPipe detector on first call

This module owns detection only — no mesh, no gaze, no emotion.

NOTE: The face_crop output is no longer consumed by the emotion model.
Emotion inference now uses MediaPipe FaceLandmarker (which handles face
detection internally). This module is still used for face presence
detection and by the gaze tracker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import mediapipe as mp

logger = logging.getLogger(__name__)

# Path to the downloaded model file
_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "mediapipe" / "blaze_face_short_range.tflite"


@dataclass
class FaceDetectionResult:
    """Result of a single face detection."""
    bbox: tuple[int, int, int, int]     # (x, y, w, h) in pixels
    confidence: float                    # 0 – 1
    face_crop: np.ndarray               # cropped face region (BGR)


class FaceDetector:
    """Thin wrapper around MediaPipe FaceDetector Task API.

    Parameters
    ----------
    min_confidence : float
        Minimum detection confidence (0–1). Default 0.5.
    model_path : Path | None
        Override path to the .tflite model file.
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        model_path: Optional[Path] = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._model_path = model_path or _MODEL_PATH
        self._detector: Optional[mp.tasks.vision.FaceDetector] = None

    # ── lazy init ────────────────────────────────────────────────────
    def _ensure_detector(self) -> None:
        if self._detector is not None:
            return

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"MediaPipe face detection model not found at {self._model_path}. "
                "Download from: https://storage.googleapis.com/mediapipe-models/"
                "face_detector/blaze_face_short_range/float16/latest/"
                "blaze_face_short_range.tflite"
            )

        base_options = mp.tasks.BaseOptions(
            model_asset_path=str(self._model_path)
        )
        options = mp.tasks.vision.FaceDetectorOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=self._min_confidence,
        )
        self._detector = mp.tasks.vision.FaceDetector.create_from_options(options)
        logger.info(
            "FaceDetector initialised (Task API, confidence=%.2f)",
            self._min_confidence,
        )

    # ── public API ───────────────────────────────────────────────────
    def detect(self, frame: np.ndarray) -> list[FaceDetectionResult]:
        """Detect faces in a BGR frame.

        Returns a list of FaceDetectionResult sorted by confidence (desc).
        """
        self._ensure_detector()

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(mp_image)

        detections: list[FaceDetectionResult] = []
        if not result.detections:
            return detections

        for det in result.detections:
            bbox = det.bounding_box
            score = det.categories[0].score if det.categories else 0.0

            if score < self._min_confidence:
                continue

            x = max(0, bbox.origin_x)
            y = max(0, bbox.origin_y)
            bw = min(bbox.width, w - x)
            bh = min(bbox.height, h - y)

            if bw <= 0 or bh <= 0:
                continue

            crop = frame[y : y + bh, x : x + bw].copy()

            detections.append(
                FaceDetectionResult(
                    bbox=(x, y, bw, bh),
                    confidence=float(score),
                    face_crop=crop,
                )
            )

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def detect_primary(self, frame: np.ndarray) -> Optional[FaceDetectionResult]:
        """Return the highest-confidence face, or None."""
        dets = self.detect(frame)
        return dets[0] if dets else None

    def close(self) -> None:
        if self._detector is not None:
            self._detector.close()
            self._detector = None
