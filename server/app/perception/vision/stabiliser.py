"""
Prediction Stabiliser — Temporal smoothing for vision predictions.

Maintains a sliding window of K recent predictions and applies
majority voting (for discrete labels like gaze) and exponential
moving average (for continuous confidence values).

This eliminates jitter from frame-to-frame noise without adding
perceptible latency.
"""

from __future__ import annotations

import logging
from collections import Counter, deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SIZE = 7      # number of recent predictions to keep


@dataclass
class StabilisedPrediction:
    """Smoothed output from the stabiliser."""
    emotion_label: str
    emotion_confidence: float
    gaze_state: str
    raw_emotion_label: str      # before smoothing
    raw_gaze_state: str         # before smoothing


class PredictionStabiliser:
    """Temporal smoothing for gaze + emotion predictions.

    Strategies:
      • Gaze:    majority vote over last K frames
      • Emotion: majority vote for label, EMA for confidence

    Parameters
    ----------
    window_size : int
        Number of past predictions to consider.
    ema_alpha : float
        Smoothing factor for confidence EMA (0 < α ≤ 1).
        Higher = more responsive, lower = smoother.
    """

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW_SIZE,
        ema_alpha: float = 0.3,
    ) -> None:
        self._window_size = window_size
        self._ema_alpha = ema_alpha

        self._gaze_history: deque[str] = deque(maxlen=window_size)
        self._emotion_history: deque[str] = deque(maxlen=window_size)
        self._confidence_ema: Optional[float] = None

    def update(
        self,
        emotion_label: str,
        emotion_confidence: float,
        gaze_state: str,
    ) -> StabilisedPrediction:
        """Push a new prediction and return the stabilised result."""

        self._gaze_history.append(gaze_state)
        self._emotion_history.append(emotion_label)

        # ── EMA for confidence ───────────────────────────────────
        if self._confidence_ema is None:
            self._confidence_ema = emotion_confidence
        else:
            self._confidence_ema = (
                self._ema_alpha * emotion_confidence
                + (1 - self._ema_alpha) * self._confidence_ema
            )

        # ── Majority vote for labels ─────────────────────────────
        stable_gaze = self._majority_vote(self._gaze_history)
        stable_emotion = self._majority_vote(self._emotion_history)

        return StabilisedPrediction(
            emotion_label=stable_emotion,
            emotion_confidence=round(self._confidence_ema, 4),
            gaze_state=stable_gaze,
            raw_emotion_label=emotion_label,
            raw_gaze_state=gaze_state,
        )

    @staticmethod
    def _majority_vote(history: deque[str]) -> str:
        """Return the most common element. Ties → last seen wins."""
        if not history:
            return "neutral"
        counter = Counter(history)
        max_count = counter.most_common(1)[0][1]
        # Among tied candidates, prefer the most recent one
        for item in reversed(history):
            if counter[item] == max_count:
                return item
        return counter.most_common(1)[0][0]

    def reset(self) -> None:
        """Clear all history."""
        self._gaze_history.clear()
        self._emotion_history.clear()
        self._confidence_ema = None
