"""
Perception Change Detector — Per-session delta tracker.

Compares incoming perception values against the last-seen state and
reports only *meaningful* changes, preventing downstream systems (event
logger, agent pipeline) from triggering on every noisy frame update.

Rules
~~~~~
* **Emotion**: changed if the label differs OR the confidence delta
  exceeds ``CONFIDENCE_THRESHOLD`` (default 0.2).
* **Gaze**: changed if the gaze state string differs.
* **Transcript**: new if the text is non-empty and differs from the
  previously seen transcript.

Thread-safety: instances are designed to be used from a *single*
asyncio task chain per session.  No locking overhead.

Usage::

    from app.services.change_detector import ChangeDetector

    detector = ChangeDetector()
    delta = detector.detect(
        emotion_label="happy",
        emotion_confidence=0.85,
        gaze="on_screen",
        transcript="hello",
    )
    if delta.any_changed:
        ...  # fire event
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


# ── Configuration ────────────────────────────────────────────────────────

CONFIDENCE_THRESHOLD: float = 0.2  # minimum confidence delta to trigger


# ── Output ───────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class ChangeResult:
    """Immutable result of a change-detection pass."""

    emotion_changed: bool = False
    gaze_changed: bool = False
    new_transcript: bool = False

    @property
    def any_changed(self) -> bool:
        """Return ``True`` if *any* channel changed."""
        return self.emotion_changed or self.gaze_changed or self.new_transcript

    def to_dict(self) -> dict:
        return {
            "emotion_changed": self.emotion_changed,
            "gaze_changed": self.gaze_changed,
            "new_transcript": self.new_transcript,
        }


# ── Detector ─────────────────────────────────────────────────────────────


class ChangeDetector:
    """Stateful per-session change detector.

    Lightweight — no locks, no I/O.  Just compare-and-swap on simple
    Python attributes.

    Parameters
    ----------
    confidence_threshold : float
        Minimum absolute confidence difference to count as an emotion
        change when the label stays the same.
    """

    def __init__(
        self,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._confidence_threshold = confidence_threshold

        # ── Last-seen state ──────────────────────────────────────
        self._last_emotion_label: Optional[str] = None
        self._last_emotion_confidence: float = 0.0
        self._last_gaze: Optional[str] = None
        self._last_transcript: Optional[str] = None

    # ── Core API ─────────────────────────────────────────────────────

    def detect(
        self,
        emotion_label: str,
        emotion_confidence: float,
        gaze: str,
        transcript: str = "",
    ) -> ChangeResult:
        """Compare incoming values against last-seen state.

        Updates internal state and returns a :class:`ChangeResult`
        indicating which channels changed meaningfully.
        """
        emotion_changed = self._check_emotion(emotion_label, emotion_confidence)
        gaze_changed = self._check_gaze(gaze)
        new_transcript = self._check_transcript(transcript)

        return ChangeResult(
            emotion_changed=emotion_changed,
            gaze_changed=gaze_changed,
            new_transcript=new_transcript,
        )

    # ── Internals ────────────────────────────────────────────────────

    def _check_emotion(self, label: str, confidence: float) -> bool:
        """Detect meaningful emotion change."""
        changed = False

        if self._last_emotion_label is None:
            # First observation — always counts as a change
            changed = True
        elif label != self._last_emotion_label:
            changed = True
        elif abs(confidence - self._last_emotion_confidence) >= self._confidence_threshold:
            changed = True

        if changed:
            self._last_emotion_label = label
            self._last_emotion_confidence = confidence

        return changed

    def _check_gaze(self, gaze: str) -> bool:
        """Detect gaze state change."""
        if self._last_gaze is None or gaze != self._last_gaze:
            self._last_gaze = gaze
            return True
        return False

    def _check_transcript(self, transcript: str) -> bool:
        """Detect new, non-empty transcript."""
        text = transcript.strip() if transcript else ""
        if not text:
            return False
        if text != self._last_transcript:
            self._last_transcript = text
            return True
        return False

    # ── Utility ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all last-seen state (e.g. on session restart)."""
        self._last_emotion_label = None
        self._last_emotion_confidence = 0.0
        self._last_gaze = None
        self._last_transcript = None

    @property
    def state(self) -> dict:
        """Return current last-seen values (for debugging)."""
        return {
            "last_emotion_label": self._last_emotion_label,
            "last_emotion_confidence": self._last_emotion_confidence,
            "last_gaze": self._last_gaze,
            "last_transcript": self._last_transcript,
        }
