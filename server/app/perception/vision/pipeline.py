"""
Vision Pipeline — Orchestrates face detection, gaze tracking,
emotion inference, and prediction stabilisation.

Design principles:
  • Pulls frames from the per-session FrameBuffer (non-blocking)
  • Processes only every Nth frame to control CPU load
  • Maintains a small rolling buffer of recent frames for the CNN-LSTM
  • All heavy work runs in an asyncio executor to avoid blocking the event loop
  • Returns a clean, stabilised output dict

Usage:
    pipeline = VisionPipeline(session_id="abc")
    await pipeline.start()      # begins background processing loop
    ...
    result = pipeline.latest    # read the most recent result (non-blocking)
    ...
    await pipeline.stop()       # clean shutdown
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.services.frame_buffer import frame_buffer_manager, FrameEntry
from app.perception.vision.face_detection import FaceDetector
from app.perception.vision.gaze_tracking import GazeTracker
from app.perception.vision.emotion_model import EmotionInferenceEngine
from app.perception.vision.stabiliser import PredictionStabiliser

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────
DEFAULT_PROCESS_EVERY_N = 3        # process 1-in-3 frames (~1.7 FPS @ 5 incoming)
DEFAULT_FRAME_HISTORY = 8          # rolling buffer for CNN-LSTM
DEFAULT_POLL_TIMEOUT = 0.5         # seconds to wait for a frame before retrying

# Shared thread pool for CV work (bounded to avoid starving the server)
_cv_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vision")


@dataclass
class VisionOutput:
    """Cleaned output of the vision pipeline."""
    emotion: dict          # {"label": str, "confidence": float}
    gaze: str              # "on_screen" | "off_screen" | "closed_eyes"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "emotion": self.emotion,
            "gaze": self.gaze,
            "timestamp": self.timestamp,
        }


class VisionPipeline:
    """Async vision processor for a single session.

    Reads frames from the FrameBuffer, runs detection → gaze → emotion
    → stabilisation, and exposes the latest result.

    Parameters
    ----------
    session_id : str
        Must match the session key in FrameBufferManager.
    process_every_n : int
        Skip N-1 frames between processing passes.
    frame_history : int
        Number of recent frames kept for CNN-LSTM.
    """

    def __init__(
        self,
        session_id: str,
        process_every_n: int = DEFAULT_PROCESS_EVERY_N,
        frame_history: int = DEFAULT_FRAME_HISTORY,
    ) -> None:
        self.session_id = session_id
        self._process_every_n = process_every_n
        self._frame_history = frame_history

        # ── Sub-modules (lazy-init inside their own classes) ─────
        self._face_detector = FaceDetector()
        self._gaze_tracker = GazeTracker()
        self._emotion_engine = EmotionInferenceEngine(seq_len=frame_history)
        self._stabiliser = PredictionStabiliser()

        # ── State ────────────────────────────────────────────────
        self._latest: Optional[VisionOutput] = None
        self._frame_count = 0
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # ── Metrics ──────────────────────────────────────────────
        self.frames_processed = 0
        self.faces_detected = 0
        self.inference_time_ms: float = 0.0

    # ── Latest result (non-blocking read) ────────────────────────────
    @property
    def latest(self) -> Optional[VisionOutput]:
        return self._latest

    # ── Lifecycle ────────────────────────────────────────────────────
    async def start(self) -> None:
        """Start the background processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name=f"vision-{self.session_id}")
        logger.info("VisionPipeline started  session=%s", self.session_id)

    async def stop(self) -> None:
        """Gracefully stop the processing loop and release resources."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._face_detector.close()
        self._gaze_tracker.close()
        logger.info(
            "VisionPipeline stopped  session=%s  processed=%d  faces=%d",
            self.session_id,
            self.frames_processed,
            self.faces_detected,
        )

    # ── Main loop ────────────────────────────────────────────────────
    async def _loop(self) -> None:
        """Background coroutine: pull frames → process → update latest."""
        buf = frame_buffer_manager.get(self.session_id)
        if buf is None:
            buf = await frame_buffer_manager.get_or_create(self.session_id)

        while self._running:
            # Non-blocking frame pull
            entry = await buf.get(timeout=DEFAULT_POLL_TIMEOUT)
            if entry is None:
                continue

            self._frame_count += 1

            # Skip frames (process only every Nth)
            if self._frame_count % self._process_every_n != 0:
                continue

            # Offload CV work to thread pool to avoid blocking event loop
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    _cv_executor,
                    self._process_frame,
                    entry,
                )
                if result is not None:
                    self._latest = result
            except Exception as exc:
                logger.error(
                    "VisionPipeline frame error session=%s: %s",
                    self.session_id,
                    exc,
                    exc_info=True,
                )

    # ── Per-frame processing (runs in thread) ────────────────────────
    def _process_frame(self, entry: FrameEntry) -> Optional[VisionOutput]:
        """Synchronous heavy processing — called inside executor."""
        t0 = time.perf_counter()
        frame = entry.frame

        # Guard: if frame is 1-D (raw JPEG bytes), decode first
        if frame.ndim == 1:
            import cv2
            frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
            if frame is None:
                return None

        self.frames_processed += 1

        # ── 1. Face Detection ────────────────────────────────────
        face = self._face_detector.detect_primary(frame)
        if face is None:
            # No face → push neutral defaults through stabiliser
            prediction = self._stabiliser.update(
                emotion_label="neutral",
                emotion_confidence=0.3,
                gaze_state="off_screen",
            )
            return VisionOutput(
                emotion={"label": prediction.emotion_label,
                         "confidence": prediction.emotion_confidence},
                gaze=prediction.gaze_state,
            )

        self.faces_detected += 1

        # ── 2. Gaze Tracking ────────────────────────────────────
        gaze_result = self._gaze_tracker.analyse(frame)
        gaze_state = gaze_result.state if gaze_result else "off_screen"

        # ── 3. Emotion: push face crop into sliding window ───────
        self._emotion_engine.push_face(face.face_crop)

        emotion_label = "neutral"
        emotion_conf = 0.5

        if self._emotion_engine.ready:
            emo = self._emotion_engine.predict()
            if emo is not None:
                emotion_label = emo.label
                emotion_conf = emo.confidence

        # ── 4. Stabilise ────────────────────────────────────────
        prediction = self._stabiliser.update(
            emotion_label=emotion_label,
            emotion_confidence=emotion_conf,
            gaze_state=gaze_state,
        )

        self.inference_time_ms = (time.perf_counter() - t0) * 1000

        return VisionOutput(
            emotion={"label": prediction.emotion_label,
                     "confidence": prediction.emotion_confidence},
            gaze=prediction.gaze_state,
        )

    # ── Stats ────────────────────────────────────────────────────────
    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "running": self._running,
            "frames_processed": self.frames_processed,
            "faces_detected": self.faces_detected,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "latest": self._latest.to_dict() if self._latest else None,
        }
