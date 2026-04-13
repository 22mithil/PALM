"""
Audio WebSocket — /ws/audio/{session_id}

Accepts base64-encoded audio chunks from the frontend, decodes them,
and pushes them into a per-session STT worker queue.  Transcription
happens in a background consumer — the receive loop is never blocked.

Architecture
~~~~~~~~~~~~
    WS receive loop  →  STTWorker.enqueue()  →  STT consumer  →  SessionContext

Frontend wire format (JSON text frame)::

    {
        "type": "audio_chunk",
        "data": "<base64>",
        "mimeType": "audio/webm;codecs=opus",
        "seq": 0
    }

Server → Client acks::

    { "type": "transcript", "text": "...", "seq": 0 }
"""

from __future__ import annotations

import base64
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.session_context import session_context_manager
from app.services.stt_worker import STTWorker

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/audio/{session_id}")
async def audio_websocket(websocket: WebSocket, session_id: str):
    """Accept audio chunks and dispatch them to the STT worker queue."""
    await websocket.accept()
    logger.info(
        "🎙  Audio WS connected  session=%s  client=%s",
        session_id,
        websocket.client.host if websocket.client else "unknown",
    )

    ctx = await session_context_manager.get_or_create(session_id)

    # Spin up a dedicated STT worker for this session
    worker = STTWorker(session_id, websocket)
    worker.start()

    chunks_this_connection = 0

    try:
        while True:
            # ── Receive ──────────────────────────────────────────
            msg = await websocket.receive_json()

            if msg.get("type") != "audio_chunk":
                continue

            data = msg.get("data")
            if not data:
                continue

            seq = msg.get("seq", chunks_this_connection)
            chunks_this_connection += 1
            ctx.chunks_received += 1
            ctx.last_activity = time.time()

            # ── Decode base64 → raw bytes ────────────────────────
            try:
                audio_bytes = base64.b64decode(data)
            except Exception as exc:
                logger.warning(
                    "🎙  Base64 decode failed  session=%s  seq=%d: %s",
                    session_id,
                    seq,
                    exc,
                )
                continue

            if len(audio_bytes) == 0:
                continue

            # ── Non-blocking push into the STT queue ─────────────
            worker.enqueue(audio_bytes, seq)

    except WebSocketDisconnect:
        logger.info(
            "🎙  Audio WS disconnected  session=%s  chunks=%d",
            session_id,
            chunks_this_connection,
        )
    except Exception as exc:
        logger.error(
            "🎙  Audio WS error  session=%s: %s",
            session_id,
            exc,
            exc_info=True,
        )
    finally:
        # Drain remaining queued chunks then shut down the worker
        await worker.stop()
        logger.info(
            "🎙  Audio WS closed  session=%s  total_chunks=%d  context_stats=%s",
            session_id,
            chunks_this_connection,
            ctx.stats(),
        )
