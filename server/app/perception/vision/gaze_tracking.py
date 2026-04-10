"""
Gaze Tracking — MediaPipe FaceLandmarker (Task API) gaze & eye-state estimator.

Computes three gaze states from 478 face landmarks:
  • on_screen  — both eyes open, looking forward
  • off_screen — head/eyes turned away
  • closed_eyes — Eye Aspect Ratio (EAR) below threshold

Uses the FaceLandmarker Task API (MediaPipe v0.10+) with the
`face_landmarker.task` model that includes iris landmarks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import mediapipe as mp

logger = logging.getLogger(__name__)

# Path to the downloaded model file
_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "models" / "mediapipe" / "face_landmarker.task"
)

# ── Landmark indices (FaceLandmarker 478 points) ────────────────────────
# 6-point EAR landmarks for each eye
_R_EYE_LANDMARKS = [33, 160, 158, 133, 153, 144]
_L_EYE_LANDMARKS = [362, 385, 387, 263, 373, 380]

# Iris centre landmarks (available with face_landmarker model)
_R_IRIS_CENTER = 468
_L_IRIS_CENTER = 473

# Eye corners for gaze reference
_R_EYE_INNER = 33
_R_EYE_OUTER = 133
_L_EYE_INNER = 362
_L_EYE_OUTER = 263

# Nose tip (head pose proxy)
_NOSE_TIP = 1

# ── Thresholds ───────────────────────────────────────────────────────────
EAR_CLOSED_THRESHOLD = 0.20       # below this → eyes closed
GAZE_YAW_THRESHOLD   = 0.28       # normalised x-offset from centre
GAZE_PITCH_THRESHOLD = 0.32       # normalised y-offset from centre

GazeState = str   # "on_screen" | "off_screen" | "closed_eyes"


@dataclass
class GazeResult:
    """Output of gaze analysis for a single frame."""
    state: GazeState
    ear_left: float          # Eye Aspect Ratio – left
    ear_right: float         # Eye Aspect Ratio – right
    yaw_offset: float        # horizontal gaze offset (0 = centred)
    pitch_offset: float      # vertical gaze offset (0 = centred)


def _distance(p1, p2) -> float:
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def _ear(landmarks, indices) -> float:
    """Compute Eye Aspect Ratio from 6 landmark points.

    EAR = (‖p2−p6‖ + ‖p3−p5‖) / (2 · ‖p1−p4‖)
    """
    p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in indices]
    vertical_1 = _distance(p2, p6)
    vertical_2 = _distance(p3, p5)
    horizontal = _distance(p1, p4)
    if horizontal < 1e-6:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


class GazeTracker:
    """MediaPipe FaceLandmarker-based gaze estimator (Task API).

    Parameters
    ----------
    model_path : Path | None
        Override path to the .task model file.
    min_detection_confidence : float
    min_tracking_confidence : float
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._model_path = model_path or _MODEL_PATH
        self._det_conf = min_detection_confidence
        self._trk_conf = min_tracking_confidence
        self._landmarker: Optional[mp.tasks.vision.FaceLandmarker] = None

    # ── lazy init ────────────────────────────────────────────────────
    def _ensure_landmarker(self) -> None:
        if self._landmarker is not None:
            return

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"MediaPipe face landmarker model not found at {self._model_path}. "
                "Download from: https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
            )

        base_options = mp.tasks.BaseOptions(
            model_asset_path=str(self._model_path)
        )
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=self._det_conf,
            min_tracking_confidence=self._trk_conf,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        logger.info("GazeTracker (FaceLandmarker Task API) initialised")

    # ── public API ───────────────────────────────────────────────────
    def analyse(self, frame: np.ndarray) -> Optional[GazeResult]:
        """Analyse gaze in a BGR frame.

        Returns GazeResult or None if no face landmarks found.
        """
        self._ensure_landmarker()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)

        if not result.face_landmarks or len(result.face_landmarks) == 0:
            return None

        lm = result.face_landmarks[0]   # list of NormalizedLandmark

        # ── EAR ──────────────────────────────────────────────────
        ear_r = _ear(lm, _R_EYE_LANDMARKS)
        ear_l = _ear(lm, _L_EYE_LANDMARKS)
        avg_ear = (ear_r + ear_l) / 2.0

        # ── Gaze direction ───────────────────────────────────────
        # Check if iris landmarks are available (478-point model)
        has_iris = len(lm) > _L_IRIS_CENTER

        if has_iris:
            r_iris = lm[_R_IRIS_CENTER]
            l_iris = lm[_L_IRIS_CENTER]

            # Eye corner midpoints (horizontal reference)
            r_inner, r_outer = lm[_R_EYE_INNER], lm[_R_EYE_OUTER]
            l_inner, l_outer = lm[_L_EYE_INNER], lm[_L_EYE_OUTER]

            r_centre_x = (r_inner.x + r_outer.x) / 2
            l_centre_x = (l_inner.x + l_outer.x) / 2
            r_centre_y = (r_inner.y + r_outer.y) / 2
            l_centre_y = (l_inner.y + l_outer.y) / 2

            yaw_r = r_iris.x - r_centre_x
            yaw_l = l_iris.x - l_centre_x
            pitch_r = r_iris.y - r_centre_y
            pitch_l = l_iris.y - l_centre_y

            yaw_offset = (yaw_r + yaw_l) / 2
            pitch_offset = (pitch_r + pitch_l) / 2
        else:
            # Fallback: use nose tip deviation from frame centre
            nose = lm[_NOSE_TIP]
            yaw_offset = nose.x - 0.5
            pitch_offset = nose.y - 0.5

        # ── Classify state ───────────────────────────────────────
        if avg_ear < EAR_CLOSED_THRESHOLD:
            state: GazeState = "closed_eyes"
        elif abs(yaw_offset) > GAZE_YAW_THRESHOLD or abs(pitch_offset) > GAZE_PITCH_THRESHOLD:
            state = "off_screen"
        else:
            state = "on_screen"

        return GazeResult(
            state=state,
            ear_left=ear_l,
            ear_right=ear_r,
            yaw_offset=yaw_offset,
            pitch_offset=pitch_offset,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
