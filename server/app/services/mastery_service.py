"""
Mastery service — DB operations for student mastery scores.

Provides helpers to fetch, upsert, and adjust mastery scores in the
``mastery_scores`` table.  Used by the Mastery Agent to persist
assessment results.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mastery import MasteryScore

logger = logging.getLogger(__name__)


async def get_mastery(
    db: AsyncSession,
    student_id: uuid.UUID,
    topic: str,
    grade: int,
    subtopic: Optional[str] = None,
) -> Optional[MasteryScore]:
    """Fetch a mastery row for a student + topic (+ optional subtopic)."""
    stmt = select(MasteryScore).where(
        MasteryScore.student_id == student_id,
        MasteryScore.topic == topic,
        MasteryScore.grade == grade,
    )
    if subtopic:
        stmt = stmt.where(MasteryScore.subtopic == subtopic)
    else:
        stmt = stmt.where(MasteryScore.subtopic.is_(None))

    result = await db.execute(stmt)
    return result.scalars().first()


async def upsert_mastery(
    db: AsyncSession,
    student_id: uuid.UUID,
    topic: str,
    grade: int,
    new_score: float,
    subtopic: Optional[str] = None,
) -> MasteryScore:
    """Create or update a mastery score row.

    If the row exists, updates ``score``, increments ``attempts``,
    and refreshes ``last_updated``.  Otherwise creates a new row.

    Parameters
    ----------
    new_score : float
        The updated mastery score, clamped to [0.0, 1.0].

    Returns
    -------
    MasteryScore
        The persisted mastery row.
    """
    clamped = max(0.0, min(1.0, new_score))

    existing = await get_mastery(db, student_id, topic, grade, subtopic)

    if existing is not None:
        existing.score = clamped
        existing.attempts += 1
        existing.last_updated = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(existing)
        logger.info(
            "Updated mastery  student=%s  topic=%s  score=%.3f  attempts=%d",
            student_id,
            topic,
            clamped,
            existing.attempts,
        )
        return existing

    # Create new row
    row = MasteryScore(
        student_id=student_id,
        grade=grade,
        topic=topic,
        subtopic=subtopic,
        score=clamped,
        attempts=1,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    logger.info(
        "Created mastery  student=%s  topic=%s  score=%.3f",
        student_id,
        topic,
        clamped,
    )
    return row


async def adjust_mastery(
    db: AsyncSession,
    student_id: uuid.UUID,
    topic: str,
    grade: int,
    delta: float,
    subtopic: Optional[str] = None,
) -> tuple[MasteryScore, float]:
    """Apply a delta adjustment to an existing mastery score.

    If no row exists, creates one with ``score = max(0, delta)``.

    Returns
    -------
    tuple[MasteryScore, float]
        The updated row and the actual delta applied (after clamping).
    """
    existing = await get_mastery(db, student_id, topic, grade, subtopic)

    if existing is not None:
        old_score = existing.score
        new_score = max(0.0, min(1.0, old_score + delta))
        actual_delta = new_score - old_score
        return await upsert_mastery(
            db, student_id, topic, grade, new_score, subtopic
        ), actual_delta

    # No existing row — create with the delta as initial score
    initial = max(0.0, min(1.0, delta))
    row = await upsert_mastery(
        db, student_id, topic, grade, initial, subtopic
    )
    return row, initial
