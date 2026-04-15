"""
Context Aggregator — RAW → STRUCTURED context builder.

Merges three input sources into a single structured dict that
downstream agents (Orchestrator, Dialogue, Engagement) consume:

  1. **Session perception** — emotion, gaze, latest transcript
     (from ``SessionContext`` in-memory state)
  2. **Database**           — mastery_score, session summary
     (from ``mastery_scores`` / ``sessions`` tables via SQLAlchemy)
  3. **In-memory session**  — current topic, difficulty, response history
     (tracked locally per session by this module)

Output schema::

    {
      "student_id":      str,
      "session_id":      str,
      "query":           str,              # latest transcript
      "emotion":         {"label": str, "confidence": float},
      "gaze":            str,
      "current_topic":   str | None,
      "difficulty_level": int,
      "mastery_score":   float | None,
      "last_responses":  list[str],        # rolling window, max 5
      "session_summary": str | None,
    }

Usage::

    from app.state.context_manager import context_aggregator

    ctx = await context_aggregator.build(
        student_id="...",
        session_id="...",
        db=async_session,
    )
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mastery import MasteryScore
from app.models.session import Session as SessionModel
from app.services.session_context import session_context_manager

logger = logging.getLogger(__name__)

MAX_LAST_RESPONSES = 5


# ── Per-session metadata (topic, difficulty, response history) ───────────


class _SessionMeta:
    """Lightweight in-memory metadata for one active session.

    Tracks state that is *not* persisted in the DB but is needed
    by the aggregator: current topic being discussed, difficulty
    level, and a rolling window of the last N agent responses.
    """

    __slots__ = (
        "current_topic",
        "difficulty_level",
        "_last_responses",
        "_lock",
    )

    def __init__(self) -> None:
        self.current_topic: Optional[str] = None
        self.difficulty_level: int = 1
        self._last_responses: deque[str] = deque(maxlen=MAX_LAST_RESPONSES)
        self._lock = asyncio.Lock()

    async def push_response(self, response: str) -> None:
        """Append an agent response (thread-safe, auto-evicts oldest)."""
        async with self._lock:
            self._last_responses.append(response)

    async def set_topic(self, topic: str) -> None:
        async with self._lock:
            self.current_topic = topic

    async def set_difficulty(self, level: int) -> None:
        async with self._lock:
            self.difficulty_level = level

    async def get_last_responses(self) -> list[str]:
        async with self._lock:
            return list(self._last_responses)

    def snapshot(self) -> dict[str, Any]:
        """Non-blocking read (safe for single-threaded asyncio)."""
        return {
            "current_topic": self.current_topic,
            "difficulty_level": self.difficulty_level,
            "last_responses": list(self._last_responses),
        }


# ── Context Aggregator ───────────────────────────────────────────────────


class ContextAggregator:
    """Merges perception, DB, and in-memory state into a structured dict.

    Maintains a registry of ``_SessionMeta`` objects keyed by session_id,
    providing helpers to update topic, difficulty, and responses from
    anywhere in the pipeline.

    The primary entry-point is :meth:`build`, which pulls data from all
    three sources and returns a flat, agent-ready dict.
    """

    def __init__(self) -> None:
        self._meta: dict[str, _SessionMeta] = {}
        self._meta_lock = asyncio.Lock()

    # ── Session meta lifecycle ───────────────────────────────────────

    async def _get_or_create_meta(self, session_id: str) -> _SessionMeta:
        async with self._meta_lock:
            if session_id not in self._meta:
                self._meta[session_id] = _SessionMeta()
                logger.debug("Created session meta for session=%s", session_id)
            return self._meta[session_id]

    async def remove_session(self, session_id: str) -> None:
        """Clean up session metadata on session end."""
        async with self._meta_lock:
            removed = self._meta.pop(session_id, None)
            if removed:
                logger.info("Removed session meta for session=%s", session_id)

    # ── Mutation helpers (called by orchestrator / agents) ───────────

    async def push_response(self, session_id: str, response: str) -> None:
        """Record an agent response in the rolling window."""
        meta = await self._get_or_create_meta(session_id)
        await meta.push_response(response)

    async def set_topic(self, session_id: str, topic: str) -> None:
        """Update the current topic being discussed."""
        meta = await self._get_or_create_meta(session_id)
        await meta.set_topic(topic)

    async def set_difficulty(self, session_id: str, level: int) -> None:
        """Update the current difficulty level."""
        meta = await self._get_or_create_meta(session_id)
        await meta.set_difficulty(level)

    # ── DB lookups ───────────────────────────────────────────────────

    @staticmethod
    async def _fetch_mastery_score(
        db: AsyncSession,
        student_id: uuid.UUID,
        topic: Optional[str],
    ) -> Optional[float]:
        """Fetch the latest mastery score for a student + topic.

        Returns ``None`` if no mastery row exists yet.
        """
        if not topic:
            return None
        try:
            result = await db.execute(
                select(MasteryScore.score)
                .where(
                    MasteryScore.student_id == student_id,
                    MasteryScore.topic == topic,
                )
                .order_by(MasteryScore.last_updated.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return float(row) if row is not None else None
        except Exception:
            logger.exception("Failed to fetch mastery score for student=%s topic=%s", student_id, topic)
            return None

    @staticmethod
    async def _fetch_session_summary(
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[str]:
        """Fetch the session summary from the DB (may be null for active sessions)."""
        try:
            result = await db.execute(
                select(SessionModel.summary).where(SessionModel.id == session_id)
            )
            return result.scalar_one_or_none()
        except Exception:
            logger.exception("Failed to fetch session summary for session=%s", session_id)
            return None

    # ── Primary entry-point ──────────────────────────────────────────

    async def build(
        self,
        student_id: str,
        session_id: str,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Aggregate all context sources into a structured dict.

        Pulls from:
          • ``session_context_manager`` → perception (emotion, gaze) + latest transcript
          • ``_SessionMeta``            → topic, difficulty, last_responses
          • DB (mastery_scores, sessions) → mastery_score, session_summary

        Parameters
        ----------
        student_id : str
            UUID string of the current student.
        session_id : str
            UUID string of the current session.
        db : AsyncSession
            Active SQLAlchemy async session for DB reads.

        Returns
        -------
        dict
            Structured context dict ready for agent consumption.
        """

        # ── 1. In-memory perception (emotion, gaze, transcript) ──────
        session_ctx = session_context_manager.get(session_id)

        if session_ctx is not None:
            perception = await session_ctx.get_perception()
            query = await session_ctx.get_recent_transcript(n=1)
            emotion = {
                "label": perception.emotion_label,
                "confidence": round(perception.emotion_confidence, 3),
            }
            gaze = perception.gaze
        else:
            logger.warning("No session context found for session=%s", session_id)
            query = ""
            emotion = {"label": "unknown", "confidence": 0.0}
            gaze = "unknown"

        # ── 2. In-memory session meta (topic, difficulty, history) ───
        meta = await self._get_or_create_meta(session_id)
        meta_snap = meta.snapshot()

        # Resolve topic: prefer meta override, fall back to perception context
        current_topic = meta_snap["current_topic"]

        # ── 3. DB lookups (mastery + summary) — run concurrently ─────
        student_uuid = uuid.UUID(student_id)
        session_uuid = uuid.UUID(session_id)

        mastery_score, session_summary = await asyncio.gather(
            self._fetch_mastery_score(db, student_uuid, current_topic),
            self._fetch_session_summary(db, session_uuid),
        )

        # ── 4. Assemble structured output ────────────────────────────
        structured: dict[str, Any] = {
            "student_id": student_id,
            "session_id": session_id,
            "query": query,
            "emotion": emotion,
            "gaze": gaze,
            "current_topic": current_topic,
            "difficulty_level": meta_snap["difficulty_level"],
            "mastery_score": mastery_score,
            "last_responses": meta_snap["last_responses"],
            "session_summary": session_summary,
        }

        logger.debug(
            "Context aggregated  session=%s  topic=%s  mastery=%s",
            session_id,
            current_topic,
            mastery_score,
        )

        return structured


# ── Singleton ────────────────────────────────────────────────────────────
context_aggregator = ContextAggregator()
