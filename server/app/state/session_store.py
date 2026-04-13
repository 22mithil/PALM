"""
Session Store — In-memory per-session perception state.

Holds the *latest* perception snapshot for each active session:
emotion, gaze, transcript, and a last-updated timestamp.  Designed
for fast reads by downstream agents (Orchestrator, Engagement, etc.)
that need the current learner state without scanning full history.

Thread-safety: all mutations go through an ``asyncio.Lock`` per
session, so concurrent WebSocket handlers (video, audio) can update
the same session safely.

Usage::

    from app.state.session_store import session_store

    await session_store.create("sess-1")
    await session_store.update_emotion("sess-1", "happy", 0.92)
    ctx = await session_store.get("sess-1")
    print(ctx.latest_emotion)   # EmotionSnapshot(label='happy', confidence=0.92)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class EmotionSnapshot:
    """Most recent emotion inference result."""

    label: str = ""
    confidence: float = 0.0


@dataclass
class SessionState:
    """Per-session perception state.

    Attributes
    ----------
    session_id : str
        Unique session identifier.
    latest_emotion : EmotionSnapshot
        Most recent detected emotion.
    latest_gaze : str
        Most recent gaze direction (e.g. ``"on-screen"``, ``"away"``).
    latest_transcript : str
        Most recent STT transcript chunk.
    last_updated : float
        Epoch timestamp of the last field update.
    created_at : float
        Epoch timestamp when the session was created.
    """

    session_id: str
    latest_emotion: EmotionSnapshot = field(default_factory=EmotionSnapshot)
    latest_gaze: str = ""
    latest_transcript: str = ""
    last_updated: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)

    # Internal lock — not part of the public API
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, repr=False, compare=False
    )

    def snapshot(self) -> dict:
        """Return a plain-dict snapshot (safe to serialize / log)."""
        return {
            "session_id": self.session_id,
            "latest_emotion": {
                "label": self.latest_emotion.label,
                "confidence": self.latest_emotion.confidence,
            },
            "latest_gaze": self.latest_gaze,
            "latest_transcript": self.latest_transcript,
            "last_updated": self.last_updated,
            "created_at": self.created_at,
        }


# ── Store ────────────────────────────────────────────────────────────────


class SessionStore:
    """Global in-memory registry of per-session perception state.

    Supports concurrent sessions; each session has its own lock to
    avoid cross-session contention on updates.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._global_lock = asyncio.Lock()

    # ── Create / Delete ──────────────────────────────────────────────

    async def create(self, session_id: str) -> SessionState:
        """Create a new session state (idempotent — returns existing if present)."""
        async with self._global_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
                logger.info("Session state created  session=%s", session_id)
            return self._sessions[session_id]

    async def remove(self, session_id: str) -> None:
        """Remove a session state (no-op if not found)."""
        async with self._global_lock:
            state = self._sessions.pop(session_id, None)
            if state:
                logger.info(
                    "Session state removed  session=%s  snapshot=%s",
                    session_id,
                    state.snapshot(),
                )

    # ── Read ─────────────────────────────────────────────────────────

    async def get(self, session_id: str) -> Optional[SessionState]:
        """Return the session state, or ``None`` if it doesn't exist."""
        return self._sessions.get(session_id)

    async def get_snapshot(self, session_id: str) -> Optional[dict]:
        """Return a serializable dict snapshot, or ``None``."""
        state = self._sessions.get(session_id)
        if state is None:
            return None
        async with state._lock:
            return state.snapshot()

    # ── Partial Updates ──────────────────────────────────────────────

    async def update_emotion(
        self, session_id: str, label: str, confidence: float
    ) -> None:
        """Update the latest emotion for a session."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(
                "update_emotion called for unknown session=%s", session_id
            )
            return
        async with state._lock:
            state.latest_emotion = EmotionSnapshot(
                label=label, confidence=confidence
            )
            state.last_updated = time.time()

    async def update_gaze(self, session_id: str, gaze: str) -> None:
        """Update the latest gaze direction for a session."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(
                "update_gaze called for unknown session=%s", session_id
            )
            return
        async with state._lock:
            state.latest_gaze = gaze
            state.last_updated = time.time()

    async def update_transcript(self, session_id: str, transcript: str) -> None:
        """Update the latest transcript chunk for a session."""
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning(
                "update_transcript called for unknown session=%s", session_id
            )
            return
        async with state._lock:
            state.latest_transcript = transcript
            state.last_updated = time.time()

    # ── Bulk / Utility ───────────────────────────────────────────────

    @property
    def active_session_ids(self) -> list[str]:
        """Return IDs of all active sessions."""
        return list(self._sessions.keys())

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    async def all_snapshots(self) -> dict[str, dict]:
        """Return snapshots for every active session (for debugging)."""
        result = {}
        for sid, state in self._sessions.items():
            async with state._lock:
                result[sid] = state.snapshot()
        return result


# ── Singleton ────────────────────────────────────────────────────────────

session_store = SessionStore()
