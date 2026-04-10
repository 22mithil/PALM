"""
Emotion Inference — CNN-LSTM model wrapper for temporal emotion recognition.

Operates on a SEQUENCE of face crops (not a single frame) to capture
temporal dynamics (e.g., gradual confusion vs. sudden frustration).

Architecture (expected model):
  Input  → (seq_len, 48, 48, 1) grayscale face crops
  CNN    → per-frame spatial features
  LSTM   → temporal aggregation
  Dense  → softmax over 5 classes

Labels:
  ["confident", "confused", "bored", "frustrated", "neutral"]

If no pretrained model file is found, falls back to a lightweight
heuristic estimator so the pipeline never crashes.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────
EMOTION_LABELS = ["confident", "confused", "bored", "frustrated", "neutral"]
NUM_CLASSES = len(EMOTION_LABELS)

# CNN-LSTM expects this input shape per frame
FACE_INPUT_SIZE = (48, 48)
DEFAULT_SEQ_LEN = 8            # number of frames per inference window

# Path to the pretrained .h5 / .keras / .onnx model
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "emotion"
MODEL_CANDIDATES = [
    MODEL_DIR / "emotion_cnn_lstm.keras",
    MODEL_DIR / "emotion_cnn_lstm.h5",
    MODEL_DIR / "emotion_cnn_lstm.onnx",
]


@dataclass
class EmotionResult:
    """Emotion prediction for a frame sequence."""
    label: str              # one of EMOTION_LABELS
    confidence: float       # 0 – 1
    probabilities: dict[str, float]   # label → prob


def _preprocess_face(face_crop: np.ndarray) -> np.ndarray:
    """Resize + grayscale + normalise a single face crop.

    Returns shape (48, 48, 1), dtype float32, range [0, 1].
    """
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, FACE_INPUT_SIZE, interpolation=cv2.INTER_AREA)
    normalised = resized.astype(np.float32) / 255.0
    return normalised[..., np.newaxis]  # (48, 48, 1)


class EmotionInferenceEngine:
    """Temporal emotion recogniser using a pretrained CNN-LSTM.

    Maintains a sliding window of preprocessed face frames:
      • Call `push_face(crop)` for each new face crop.
      • Call `predict()` to run inference on the current window.

    Parameters
    ----------
    seq_len : int
        Number of frames in the temporal window.
    model_path : Path | None
        Override path to the model file.
    """

    def __init__(
        self,
        seq_len: int = DEFAULT_SEQ_LEN,
        model_path: Optional[Path] = None,
    ) -> None:
        self._seq_len = seq_len
        self._window: deque[np.ndarray] = deque(maxlen=seq_len)
        self._model = None
        self._model_path = model_path
        self._use_fallback = False
        self._loaded = False

    # ── lazy load ────────────────────────────────────────────────────
    def _load_model(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        path = self._model_path
        if path is None:
            for candidate in MODEL_CANDIDATES:
                if candidate.exists():
                    path = candidate
                    break

        if path is None or not path.exists():
            logger.warning(
                "No emotion model found at %s — using heuristic fallback. "
                "Place a trained model at one of: %s",
                MODEL_DIR,
                [str(c) for c in MODEL_CANDIDATES],
            )
            self._use_fallback = True
            return

        try:
            if str(path).endswith(".onnx"):
                self._load_onnx(path)
            else:
                self._load_keras(path)
            logger.info("Emotion model loaded from %s", path)
        except Exception as exc:
            logger.error("Failed to load emotion model: %s — using fallback", exc)
            self._use_fallback = True

    def _load_keras(self, path: Path) -> None:
        try:
            from tensorflow import keras
            self._model = keras.models.load_model(str(path), compile=False)
            self._model_type = "keras"
        except ImportError:
            logger.warning("TensorFlow not installed — trying ONNX fallback")
            onnx_path = path.with_suffix(".onnx")
            if onnx_path.exists():
                self._load_onnx(onnx_path)
            else:
                self._use_fallback = True

    def _load_onnx(self, path: Path) -> None:
        try:
            import onnxruntime as ort
            self._model = ort.InferenceSession(str(path))
            self._model_type = "onnx"
        except ImportError:
            logger.warning("onnxruntime not installed — using fallback")
            self._use_fallback = True

    # ── public API ───────────────────────────────────────────────────
    def push_face(self, face_crop: np.ndarray) -> None:
        """Add a preprocessed face frame to the sliding window."""
        processed = _preprocess_face(face_crop)
        self._window.append(processed)

    @property
    def ready(self) -> bool:
        """True when the window has enough frames for inference."""
        return len(self._window) >= self._seq_len

    def predict(self) -> Optional[EmotionResult]:
        """Run inference on the current frame window.

        Returns None if the window isn't full yet.
        """
        self._load_model()

        if not self.ready:
            return None

        # Build batch: (1, seq_len, 48, 48, 1)
        seq = np.array(list(self._window), dtype=np.float32)
        batch = seq[np.newaxis, ...]

        if self._use_fallback:
            return self._fallback_predict(batch)

        try:
            if self._model_type == "keras":
                probs = self._model.predict(batch, verbose=0)[0]
            elif self._model_type == "onnx":
                input_name = self._model.get_inputs()[0].name
                probs = self._model.run(None, {input_name: batch})[0][0]
            else:
                return self._fallback_predict(batch)

            idx = int(np.argmax(probs))
            return EmotionResult(
                label=EMOTION_LABELS[idx],
                confidence=float(probs[idx]),
                probabilities={
                    lbl: float(p) for lbl, p in zip(EMOTION_LABELS, probs)
                },
            )
        except Exception as exc:
            logger.warning("Emotion inference failed: %s — using fallback", exc)
            return self._fallback_predict(batch)

    def _fallback_predict(self, batch: np.ndarray) -> EmotionResult:
        """Heuristic fallback when no ML model is available.

        Uses pixel variance and temporal change as rough proxies:
          - High variance + low change → confident
          - Low variance + high change → confused
          - Low everything → bored / neutral
        """
        seq = batch[0]  # (seq_len, 48, 48, 1)
        variances = [float(np.var(f)) for f in seq]
        avg_var = np.mean(variances)

        # Temporal difference (frame-to-frame change)
        diffs = [float(np.mean(np.abs(seq[i] - seq[i - 1])))
                 for i in range(1, len(seq))]
        avg_diff = np.mean(diffs) if diffs else 0.0

        # Simple rule-based mapping
        if avg_var > 0.06 and avg_diff < 0.02:
            label, conf = "confident", 0.55
        elif avg_diff > 0.04:
            label, conf = "confused", 0.50
        elif avg_var < 0.02:
            label, conf = "bored", 0.45
        elif avg_diff > 0.03 and avg_var > 0.04:
            label, conf = "frustrated", 0.40
        else:
            label, conf = "neutral", 0.60

        probs = {lbl: 0.1 for lbl in EMOTION_LABELS}
        probs[label] = conf
        remaining = 1.0 - conf
        others = [l for l in EMOTION_LABELS if l != label]
        for l in others:
            probs[l] = remaining / len(others)

        return EmotionResult(
            label=label,
            confidence=conf,
            probabilities=probs,
        )

    def reset(self) -> None:
        """Clear the frame window."""
        self._window.clear()
