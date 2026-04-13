"""
Video WebSocket — /ws/video/{session_id}

Accepts JPEG frames encoded as base64 from the frontend,
decodes them into numpy arrays, pushes them into the per-session
frame buffer, and starts the VisionPipeline for that session.

The receive loop is intentionally kept non-blocking:
  • base64 decoding + imdecode are CPU-light at 320×240
  • No inference or heavy processing happens here
  • The VisionPipeline runs as a separate asyncio task that pulls
    from the buffer asynchronously
"""

from __future__ import annotations

import base64
import logging
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.frame_buffer import frame_buffer_manager, FrameEntry
from app.perception.vision.pipeline import VisionPipeline
from app.services.session_context import session_context_manager
from app.services.change_detector import ChangeDetector
from app.services.event_logger import event_logger

logger = logging.getLogger(__name__)
router = APIRouter()

# Max frequency for sending perception_update messages to the client
_PERCEPTION_SEND_INTERVAL: float = 1.0  # seconds

# Registry of active pipelines per session
_active_pipelines: dict[str, VisionPipeline] = {}


async def _decode_frame(data: str) -> np.ndarray | None:
    """Decode a base64-encoded JPEG string into a numpy array.

    Returns an HxWxC uint8 array, or None if decoding fails.
    """
    try:
        raw_bytes = base64.b64decode(data)
        buf = np.frombuffer(raw_bytes, dtype=np.uint8)

        try:
            import cv2
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
        except ImportError:
            pass

        # Fallback: store raw JPEG bytes as a 1-D uint8 array
        return buf

    except Exception as exc:
        logger.warning("Frame decode failed: %s", exc)
        return None


@router.websocket("/ws/video/{session_id}")
async def video_websocket(websocket: WebSocket, session_id: str):
    """Accept a WebSocket connection, buffer incoming video frames,
    and run the vision pipeline for this session.

    Message format (JSON text frame):
        { "type": "frame", "data": "<base64 JPEG>" }

    Sends perception updates to the client on meaningful changes
    (max 1/sec)::

        {
          "type": "perception_update",
          "payload": {
            "emotion": { "label": "...", "confidence": ... },
            "gaze": "..."
          }
        }
    """
    await websocket.accept()
    logger.info(
        "🎥  Video WS connected  session=%s  client=%s",
        session_id,
        websocket.client.host if websocket.client else "unknown",
    )

    buffer = await frame_buffer_manager.get_or_create(session_id)
    ctx = await session_context_manager.get_or_create(session_id)
    detector = ChangeDetector()
    frames_this_connection = 0
    last_perception_send: float = 0.0  # monotonic clock for WS throttle

    # ── Start the vision pipeline for this session ───────────────
    pipeline = VisionPipeline(session_id=session_id)
    _active_pipelines[session_id] = pipeline
    await pipeline.start()
    logger.info("🧠  VisionPipeline started for session=%s", session_id)

    try:
        while True:
            # ── Receive ──────────────────────────────────────────
            msg = await websocket.receive_json()

            msg_type = msg.get("type")
            if msg_type != "frame":
                continue

            data = msg.get("data")
            if not data:
                continue

            # ── Decode (lightweight) ─────────────────────────────
            frame = await _decode_frame(data)
            if frame is None:
                continue

            # ── Buffer ───────────────────────────────────────────
            entry = FrameEntry(
                frame=frame,
                timestamp=time.time(),
                width=frame.shape[1] if frame.ndim >= 2 else 0,
                height=frame.shape[0] if frame.ndim >= 2 else 0,
            )
            await buffer.push(entry)
            frames_this_connection += 1

            # ── Perception check (every 10 frames) ───────────────
            if frames_this_connection % 10 == 0 and pipeline.latest:
                result = pipeline.latest

                # Always keep session context up-to-date
                await ctx.update_perception(
                    emotion_label=result.emotion["label"],
                    emotion_confidence=result.emotion["confidence"],
                    gaze=result.gaze,
                )

                # ── Change detection ─────────────────────────────
                delta = detector.detect(
                    emotion_label=result.emotion["label"],
                    emotion_confidence=result.emotion["confidence"],
                    gaze=result.gaze,
                )

                if not delta.any_changed:
                    continue

                # ── Event logging (async, throttled internally) ──
                if delta.emotion_changed:
                    await event_logger.log_emotion(
                        session_id,
                        emotion_label=result.emotion["label"],
                        gaze_status=result.gaze,
                    )
                if delta.gaze_changed:
                    await event_logger.log_gaze(
                        session_id,
                        gaze_status=result.gaze,
                        emotion_label=result.emotion["label"],
                    )

                # ── Send to frontend (max 1/sec) ────────────────
                now = time.monotonic()
                if (now - last_perception_send) < _PERCEPTION_SEND_INTERVAL:
                    continue

                last_perception_send = now
                try:
                    await websocket.send_json({
                        "type": "perception_update",
                        "payload": {
                            "emotion": result.emotion,
                            "gaze": result.gaze,
                            "gaze_tracking": {
                                "gaze_duration": round(ctx.gaze_duration, 2),
                                "gaze_away_flag": ctx.gaze_away_flag,
                            },
                        },
                    })
                except Exception:
                    pass  # Don't crash the receive loop for send errors

    except WebSocketDisconnect:
        logger.info(
            "🎥  Video WS disconnected  session=%s  frames=%d",
            session_id,
            frames_this_connection,
        )
    except Exception as exc:
        logger.error(
            "🎥  Video WS error  session=%s: %s",
            session_id,
            exc,
            exc_info=True,
        )
    finally:
        # ── Stop the vision pipeline ─────────────────────────────
        await pipeline.stop()
        _active_pipelines.pop(session_id, None)
        event_logger.clear_session(session_id)
        logger.info(
            "🎥  Video WS closed  session=%s  buffered=%d  total_received=%d  dropped=%d  pipeline_stats=%s",
            session_id,
            buffer.size,
            buffer.frames_received,
            buffer.frames_dropped,
            pipeline.stats(),
        )
