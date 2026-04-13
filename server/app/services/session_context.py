"""
Session Context — Per-session in-memory state for the tutoring pipeline.

Stores accumulated transcriptions, perception snapshots, and any other
runtime context that downstream agents (Orchestrator, Dialogue, etc.)
need to produce coherent responses.

Perception integration:
  • Vision worker  → update_perception()  → emotion + gaze
  • STT worker     → add_transcript()     → transcript entries

All updates overwrite with the latest values and track a
``last_updated`` timestamp.  Concurrent access is safe via asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

STALE_SESSION_TTL = 600  # auto-evict sessions idle > 10 min
MAX_TRANSCRIPT_ENTRIES = 200  # cap per session to bound memory


@dataclass
class PerceptionSnapshot:
    """Latest vision perception state (emotion + gaze)."""
    emotion_label: str = "neutral"
    emotion_confidence: float = 0.0
    gaze: str = "unknown"  # "on_screen" | "off_screen" | "closed_eyes"
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "emotion": {
                "label": self.emotion_label,
                "confidence": self.emotion_confidence,
            },
            "gaze": self.gaze,
            "last_updated": self.last_updated,
        }


@dataclass
class TranscriptEntry:
    """A single transcription result."""
    text: str
    timestamp: float = field(default_factory=time.time)
    seq: int = 0
    duration_hint: float = 0.0  # approx duration of the audio chunk (seconds)


# ── Gaze Duration Tracking ───────────────────────────────────────────────

_GAZE_AWAY_THRESHOLD: float = 3.0  # seconds off-screen to set flag


class GazeDurationTracker:
    """Tracks contiguous off-screen gaze duration.

    Lightweight, no I/O, no locks — designed to be called inline
    from ``update_perception()``.

    Attributes
    ----------
    duration : float
        Seconds of contiguous off-screen gaze (0.0 when on-screen).
    away_flag : bool
        ``True`` once ``duration`` exceeds ``threshold``.
    """

    __slots__ = ("_threshold", "_off_since", "duration", "away_flag")

    def __init__(self, threshold: float = _GAZE_AWAY_THRESHOLD) -> None:
        self._threshold = threshold
        self._off_since: float = 0.0   # monotonic timestamp when gaze left
        self.duration: float = 0.0
        self.away_flag: bool = False

    def update(self, gaze: str) -> None:
        """Call on every perception tick with the current gaze state."""
        now = time.monotonic()

        if gaze == "off_screen":
            if self._off_since == 0.0:
                # Just went off-screen
                self._off_since = now
            self.duration = now - self._off_since
            if self.duration > self._threshold:
                self.away_flag = True
        else:
            # on_screen / closed_eyes / unknown → reset
            self._off_since = 0.0
            self.duration = 0.0
            self.away_flag = False

    def to_dict(self) -> dict:
        return {
            "gaze_duration": round(self.duration, 2),
            "gaze_away_flag": self.away_flag,
        }


class SessionContext:
    """Runtime context for a single tutoring session.

    Accumulates transcriptions and exposes the full transcript
    as a single string for agent consumption.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.created_at: float = time.time()
        self.last_activity: float = time.time()

        # ── Perception state (vision) ────────────────────────────
        self._perception = PerceptionSnapshot()
        self._gaze_tracker = GazeDurationTracker()

        # ── Transcript state (STT) ──────────────────────────────
        self._transcripts: list[TranscriptEntry] = []

        self._lock = asyncio.Lock()

        # Counters
        self.chunks_received: int = 0
        self.chunks_transcribed: int = 0
        self.chunks_failed: int = 0

    # ── Vision perception updates ─────────────────────────────────

    async def update_perception(
        self,
        emotion_label: str,
        emotion_confidence: float,
        gaze: str,
    ) -> None:
        """Overwrite the latest perception snapshot (non-blocking, lock-safe).

        Called by the vision pipeline whenever a new frame is processed.
        Always overwrites with the most recent values.
        """
        async with self._lock:
            self._perception.emotion_label = emotion_label
            self._perception.emotion_confidence = emotion_confidence
            self._perception.gaze = gaze
            self._perception.last_updated = time.time()
            self.last_activity = time.time()

            # Update gaze duration tracker (zero-cost inline)
            self._gaze_tracker.update(gaze)

    async def get_perception(self) -> PerceptionSnapshot:
        """Return a copy of the current perception state."""
        async with self._lock:
            return PerceptionSnapshot(
                emotion_label=self._perception.emotion_label,
                emotion_confidence=self._perception.emotion_confidence,
                gaze=self._perception.gaze,
                last_updated=self._perception.last_updated,
            )

    @property
    def perception(self) -> PerceptionSnapshot:
        """Non-blocking read of the latest perception (no lock).

        Safe for *reads* from the event-loop thread because simple
        attribute assignments on a dataclass are atomic in CPython.
        Use ``get_perception()`` when a consistent snapshot is needed.
        """
        return self._perception

    # ── Gaze duration ────────────────────────────────────────────

    @property
    def gaze_duration(self) -> float:
        """Seconds of contiguous off-screen gaze (non-blocking read)."""
        return self._gaze_tracker.duration

    @property
    def gaze_away_flag(self) -> bool:
        """True if the learner has been looking away > 3 s."""
        return self._gaze_tracker.away_flag

    # ── Transcript updates (STT) ────────────────────────────────

    async def add_transcript(self, entry: TranscriptEntry) -> None:
        """Append a transcription entry (thread-safe)."""
        async with self._lock:
            self.last_activity = time.time()
            self.chunks_transcribed += 1

            self._transcripts.append(entry)

            # Evict oldest if over cap
            if len(self._transcripts) > MAX_TRANSCRIPT_ENTRIES:
                self._transcripts = self._transcripts[-MAX_TRANSCRIPT_ENTRIES:]

    async def get_full_transcript(self) -> str:
        """Return all transcriptions joined as a single string."""
        async with self._lock:
            return " ".join(
                e.text for e in self._transcripts if e.text.strip()
            )

    async def get_recent_transcript(self, n: int = 10) -> str:
        """Return the last N transcription entries joined."""
        async with self._lock:
            recent = self._transcripts[-n:]
            return " ".join(e.text for e in recent if e.text.strip())

    async def get_transcript_entries(self) -> list[TranscriptEntry]:
        """Return a copy of all transcript entries."""
        async with self._lock:
            return list(self._transcripts)

    # ── Agent-facing snapshot ────────────────────────────────────

    async def snapshot(self) -> dict[str, Any]:
        """Produce a full context snapshot for downstream agents.

        Returns a dict containing the latest perception data and
        recent transcript — everything an agent needs in one call.
        """
        async with self._lock:
            return {
                "session_id": self.session_id,
                "perception": self._perception.to_dict(),
                "gaze_tracking": self._gaze_tracker.to_dict(),
                "transcript": " ".join(
                    e.text for e in self._transcripts[-10:] if e.text.strip()
                ),
                "full_transcript_length": len(self._transcripts),
                "last_activity": self.last_activity,
            }

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_activity) > STALE_SESSION_TTL

    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "perception": self._perception.to_dict(),
            "gaze_tracking": self._gaze_tracker.to_dict(),
            "transcript_entries": len(self._transcripts),
            "chunks_received": self.chunks_received,
            "chunks_transcribed": self.chunks_transcribed,
            "chunks_failed": self.chunks_failed,
            "last_activity": self.last_activity,
        }


class SessionContextManager:
    """Global registry of per-session contexts.

    Usage:
        ctx = await session_context_manager.get_or_create("session-123")
        await ctx.add_transcript(TranscriptEntry(text="hello"))
        transcript = await ctx.get_full_transcript()
    """

    def __init__(self) -> None:
        self._contexts: dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> SessionContext:
        """Return existing context or create a new one."""
        async with self._lock:
            if session_id not in self._contexts:
                self._contexts[session_id] = SessionContext(session_id)
                logger.info("Created session context for session=%s", session_id)
            return self._contexts[session_id]

    def get(self, session_id: str) -> Optional[SessionContext]:
        """Return context if it exists, else None."""
        return self._contexts.get(session_id)

    async def remove(self, session_id: str) -> None:
        """Remove a session context (e.g. on session end)."""
        async with self._lock:
            ctx = self._contexts.pop(session_id, None)
            if ctx:
                logger.info(
                    "Removed session context  session=%s  stats=%s",
                    session_id,
                    ctx.stats(),
                )

    async def cleanup_stale(self) -> int:
        """Evict idle sessions. Returns number evicted."""
        async with self._lock:
            stale = [sid for sid, ctx in self._contexts.items() if ctx.is_stale]
            for sid in stale:
                ctx = self._contexts.pop(sid)
                logger.info(
                    "Evicted stale session context  session=%s  (idle %.0fs)",
                    sid,
                    time.time() - ctx.last_activity,
                )
            return len(stale)

    @property
    def active_sessions(self) -> list[str]:
        return list(self._contexts.keys())

    def stats(self) -> dict:
        return {sid: ctx.stats() for sid, ctx in self._contexts.items()}


# ── Singleton ────────────────────────────────────────────────────────────
session_context_manager = SessionContextManager()
