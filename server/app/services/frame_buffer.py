"""
Frame Buffer — Per-session in-memory ring buffer for decoded video frames.

Each session gets its own buffer (asyncio.Queue backed) so the WebSocket
receive loop can push frames without blocking, and downstream processors
can consume frames at their own pace.

Thread-safety: uses asyncio primitives — safe for concurrent coroutines.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────
DEFAULT_BUFFER_SIZE = 30        # ~6 seconds @ 5 FPS
STALE_SESSION_TTL = 300         # auto-evict sessions idle > 5 min


@dataclass
class FrameEntry:
    """A single decoded frame with metadata."""
    frame: np.ndarray                       # HxWxC uint8
    timestamp: float = field(default_factory=time.time)
    width: int = 0
    height: int = 0


class SessionFrameBuffer:
    """Ring buffer for a single session.

    When full, the oldest frame is silently dropped (back-pressure).
    """

    def __init__(self, maxsize: int = DEFAULT_BUFFER_SIZE) -> None:
        self._queue: asyncio.Queue[FrameEntry] = asyncio.Queue(maxsize=maxsize)
        self.last_activity: float = time.time()
        self.frames_received: int = 0
        self.frames_dropped: int = 0

    async def push(self, entry: FrameEntry) -> None:
        """Non-blocking push. Drops oldest frame if buffer is full."""
        self.last_activity = time.time()
        self.frames_received += 1

        if self._queue.full():
            try:
                self._queue.get_nowait()
                self.frames_dropped += 1
            except asyncio.QueueEmpty:
                pass

        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Shouldn't happen after the drop above, but guard anyway
            self.frames_dropped += 1

    async def get(self, timeout: Optional[float] = None) -> Optional[FrameEntry]:
        """Blocking get — waits up to `timeout` seconds for a frame."""
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return await self._queue.get()
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None

    def get_nowait(self) -> Optional[FrameEntry]:
        """Non-blocking get. Returns None if empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_activity) > STALE_SESSION_TTL

    def stats(self) -> dict:
        return {
            "buffered": self.size,
            "received": self.frames_received,
            "dropped": self.frames_dropped,
            "last_activity": self.last_activity,
        }


class FrameBufferManager:
    """Global registry of per-session frame buffers.

    Usage:
        manager = FrameBufferManager()

        # In the WebSocket handler:
        buf = manager.get_or_create("session-123")
        await buf.push(frame_entry)

        # In a downstream processor:
        buf = manager.get("session-123")
        entry = await buf.get(timeout=1.0)
    """

    def __init__(self) -> None:
        self._buffers: dict[str, SessionFrameBuffer] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self, session_id: str, maxsize: int = DEFAULT_BUFFER_SIZE
    ) -> SessionFrameBuffer:
        """Return existing buffer or create a new one."""
        async with self._lock:
            if session_id not in self._buffers:
                self._buffers[session_id] = SessionFrameBuffer(maxsize=maxsize)
                logger.info("Created frame buffer for session=%s", session_id)
            return self._buffers[session_id]

    def get(self, session_id: str) -> Optional[SessionFrameBuffer]:
        """Return buffer if it exists, else None."""
        return self._buffers.get(session_id)

    async def remove(self, session_id: str) -> None:
        """Remove a session buffer (e.g. on disconnect)."""
        async with self._lock:
            buf = self._buffers.pop(session_id, None)
            if buf:
                logger.info(
                    "Removed frame buffer for session=%s  (received=%d, dropped=%d)",
                    session_id,
                    buf.frames_received,
                    buf.frames_dropped,
                )

    async def cleanup_stale(self) -> int:
        """Evict idle sessions. Returns number of sessions evicted."""
        async with self._lock:
            stale = [sid for sid, buf in self._buffers.items() if buf.is_stale]
            for sid in stale:
                buf = self._buffers.pop(sid)
                logger.info(
                    "Evicted stale session=%s  (idle %.0fs)",
                    sid,
                    time.time() - buf.last_activity,
                )
            return len(stale)

    @property
    def active_sessions(self) -> list[str]:
        return list(self._buffers.keys())

    def stats(self) -> dict:
        return {
            sid: buf.stats() for sid, buf in self._buffers.items()
        }


# ── Singleton ────────────────────────────────────────────────────────────
frame_buffer_manager = FrameBufferManager()
