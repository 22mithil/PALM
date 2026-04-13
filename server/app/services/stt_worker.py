"""
STT Worker — Per-session async queue + consumer for speech transcription.

Architecture
~~~~~~~~~~~~
    WebSocket receive loop  →  Audio Queue  →  STT Worker  →  SessionContext

The WebSocket handler pushes raw audio chunks into a bounded queue
without blocking.  A single background task per session pulls chunks,
runs transcription, and stores results in SessionContext.

Back-pressure: when the queue is full the oldest un-consumed audio
chunk is *dropped* (with a warning) rather than blocking the WS loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from fastapi import WebSocket

from app.integrations.fastrouter.stt import transcribe_audio, STTError
from app.services.session_context import (
    session_context_manager,
    SessionContext,
    TranscriptEntry,
)
from app.services.event_logger import event_logger

logger = logging.getLogger(__name__)

_QUEUE_MAX_SIZE = 20  # bounded — applies back-pressure when STT can't keep up
_DRAIN_TIMEOUT = 30.0  # seconds to wait for in-flight work on shutdown


# ── Internal data ────────────────────────────────────────────────────────


@dataclass(slots=True)
class _AudioChunk:
    """Immutable container for a queued audio chunk."""

    audio_bytes: bytes
    seq: int
    received_at: float


# ── Worker ───────────────────────────────────────────────────────────────


class STTWorker:
    """Per-session STT processing worker.

    Consumes audio chunks from a bounded :class:`asyncio.Queue`, runs
    transcription via FastRouter, and deposits results into the
    session's :class:`SessionContext`.

    Lifecycle::

        worker = STTWorker(session_id, websocket)
        worker.start()                       # spawns background consumer
        worker.enqueue(audio_bytes, seq=0)   # called from WS loop (non-blocking)
        await worker.stop()                  # on WS disconnect — drains & exits
    """

    def __init__(self, session_id: str, websocket: WebSocket) -> None:
        self.session_id = session_id
        self._ws = websocket
        self._queue: asyncio.Queue[_AudioChunk | None] = asyncio.Queue(
            maxsize=_QUEUE_MAX_SIZE,
        )
        self._task: asyncio.Task | None = None
        self._stopped = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the background consumer task."""
        if self._task is not None:
            raise RuntimeError("STTWorker already started")
        self._task = asyncio.create_task(
            self._consumer_loop(),
            name=f"stt-worker-{self.session_id}",
        )
        logger.info("🎙  STT worker started  session=%s", self.session_id)

    async def stop(self) -> None:
        """Signal the worker to finish and wait for in-flight items.

        All queued chunks are processed before the worker exits.
        If the drain exceeds ``_DRAIN_TIMEOUT`` the task is cancelled.
        """
        if self._stopped or self._task is None:
            return
        self._stopped = True

        # Sentinel tells the consumer loop to exit after draining
        await self._queue.put(None)

        try:
            await asyncio.wait_for(self._task, timeout=_DRAIN_TIMEOUT)
        except asyncio.TimeoutError:
            self._task.cancel()
            logger.warning(
                "🎙  STT worker drain timed out, cancelled  session=%s",
                self.session_id,
            )
        except asyncio.CancelledError:
            pass

        logger.info("🎙  STT worker stopped  session=%s", self.session_id)

    # ── Producer (called from WS receive loop) ───────────────────────

    def enqueue(self, audio_bytes: bytes, seq: int) -> bool:
        """Push an audio chunk onto the queue (non-blocking).

        Returns ``True`` if enqueued, ``False`` if the queue is full
        (chunk is dropped with a warning).
        """
        if self._stopped:
            return False

        chunk = _AudioChunk(
            audio_bytes=audio_bytes,
            seq=seq,
            received_at=time.time(),
        )

        try:
            self._queue.put_nowait(chunk)
            return True
        except asyncio.QueueFull:
            logger.warning(
                "🎙  STT queue full, dropping chunk  session=%s  seq=%d  "
                "qsize=%d",
                self.session_id,
                seq,
                self._queue.qsize(),
            )
            return False

    # ── Consumer loop ────────────────────────────────────────────────

    async def _consumer_loop(self) -> None:
        """Pull chunks off the queue and transcribe them sequentially."""
        ctx = await session_context_manager.get_or_create(self.session_id)

        while True:
            chunk = await self._queue.get()

            if chunk is None:
                # Sentinel — exit after marking done
                self._queue.task_done()
                break

            await self._transcribe_chunk(chunk, ctx)
            self._queue.task_done()

    async def _transcribe_chunk(
        self,
        chunk: _AudioChunk,
        ctx: SessionContext,
    ) -> None:
        """Run STT on a single audio chunk and store the result."""
        try:
            text = await transcribe_audio(chunk.audio_bytes)

            if text and text.strip():
                entry = TranscriptEntry(
                    text=text.strip(),
                    timestamp=chunk.received_at,
                    seq=chunk.seq,
                    duration_hint=0.0,
                )
                await ctx.add_transcript(entry)

                logger.debug(
                    "🎙  Transcribed  session=%s  seq=%d  len=%d chars  "
                    "latency=%.1fs",
                    self.session_id,
                    chunk.seq,
                    len(text),
                    time.time() - chunk.received_at,
                )

                # Best-effort ack back to client
                try:
                    await self._ws.send_json({
                        "type": "transcript",
                        "text": text.strip(),
                        "seq": chunk.seq,
                    })
                except Exception:
                    pass  # WS may already be closed

                # Log as student_query event (non-blocking, throttled)
                await event_logger.log_query(
                    self.session_id,
                    query_text=text.strip(),
                )

        except STTError as exc:
            ctx.chunks_failed += 1
            logger.warning(
                "🎙  STT error  session=%s  seq=%d  status=%d: %.200s",
                self.session_id,
                chunk.seq,
                exc.status_code,
                exc.body,
            )
        except Exception as exc:
            ctx.chunks_failed += 1
            logger.error(
                "🎙  Unexpected STT failure  session=%s  seq=%d: %s",
                self.session_id,
                chunk.seq,
                exc,
                exc_info=True,
            )
