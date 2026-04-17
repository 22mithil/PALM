"""
Video WebSocket — /ws/video/{session_id}

Receives lightweight perception updates (emotion + gaze) from the
client-side MediaPipe FaceLandmarker running in useFaceMesh.js.

Previous architecture:
  - Client sent JPEG frames (base64, 320×240, ~5 FPS, ~50KB/s)
  - Server decoded frames → ran VisionPipeline (FaceDetector + GazeTracker + EmotionModel)

Current architecture:
  - Client runs FaceLandmarker locally: emotion (blendshapes) + gaze (iris landmarks)
  - Client sends only {"type": "perception_update", "emotion": str, "gaze": str} at max 1/sec
  - ~100 bytes/sec bandwidth per session (500x reduction)
  - No MediaPipe, OpenCV, or numpy dependency in this handler

Wire format (inbound JSON text frame):
    {
      "type": "perception_update",
      "emotion": "confused",
      "gaze": "off_screen",
      "timestamp": 1234567890
    }
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.session_context import session_context_manager
from app.services.change_detector import ChangeDetector
from app.services.event_logger import event_logger

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/video/{session_id}")
async def video_websocket(websocket: WebSocket, session_id: str):
    """Accept a WebSocket connection and receive client-side perception
    updates (emotion + gaze) as lightweight JSON messages.

    Updates SessionContext, runs change detection, and logs meaningful
    changes to the database via EventLogger.
    """
    await websocket.accept()
    logger.info(
        "🎥  Perception WS connected  session=%s  client=%s",
        session_id,
        websocket.client.host if websocket.client else "unknown",
    )

    ctx = await session_context_manager.get_or_create(session_id)
    detector = ChangeDetector()
    updates_received = 0

    try:
        while True:
            # ── Receive ──────────────────────────────────────────
            msg = await websocket.receive_json()

            msg_type = msg.get("type")
            if msg_type != "perception_update":
                continue

            emotion = msg.get("emotion", "neutral")
            gaze = msg.get("gaze", "on_screen")
            updates_received += 1

            # ── Update SessionContext ────────────────────────────
            # Pass emotion_confidence=1.0 since client classifier
            # doesn't produce a confidence score (threshold-based)
            await ctx.update_perception(
                emotion_label=emotion,
                emotion_confidence=1.0,
                gaze=gaze,
            )

            # ── Change detection ─────────────────────────────────
            delta = detector.detect(
                emotion_label=emotion,
                emotion_confidence=1.0,
                gaze=gaze,
            )

            if not delta.any_changed:
                continue

            # ── Event logging (async, throttled internally) ──────
            if delta.emotion_changed:
                await event_logger.log_emotion(
                    session_id,
                    emotion_label=emotion,
                    gaze_status=gaze,
                )
            if delta.gaze_changed:
                await event_logger.log_gaze(
                    session_id,
                    gaze_status=gaze,
                    emotion_label=emotion,
                )

    except WebSocketDisconnect:
        logger.info(
            "🎥  Perception WS disconnected  session=%s  updates=%d",
            session_id,
            updates_received,
        )
    except Exception as exc:
        logger.error(
            "🎥  Perception WS error  session=%s: %s",
            session_id,
            exc,
            exc_info=True,
        )
    finally:
        event_logger.clear_session(session_id)
        logger.info(
            "🎥  Perception WS closed  session=%s  total_updates=%d",
            session_id,
            updates_received,
        )
