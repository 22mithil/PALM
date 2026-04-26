"""
Section Loader — loads the current section's content from the DB.

Plain DB read, no LLM. Populates ``state.current_section`` with the
full pedagogical content (explanation, examples, hints, quiz questions)
for the student's active section.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.curriculum import ChapterSection
from app.pipeline.state import CurrentSection, TurnState

logger = logging.getLogger(__name__)


async def load_section(state: TurnState, db: AsyncSession) -> None:
    """Load the current section content into state.current_section.

    Reads from ``chapter_sections`` using the section_id stored in
    ``state.chapter_progress.current_section_id``.
    """
    if state.chapter_progress is None:
        logger.warning("No chapter_progress — skipping section load")
        return

    section_id = state.chapter_progress.current_section_id

    result = await db.execute(
        select(ChapterSection).where(ChapterSection.section_id == section_id)
    )
    row = result.scalars().first()

    if row is None:
        logger.error("Section %s not found in DB", section_id)
        return

    state.current_section = CurrentSection(
        section_id=row.section_id,
        chapter_id=row.chapter_id,
        order=row.order,
        concept=row.concept,
        title=row.title,
        difficulty=row.difficulty,
        prerequisite_concepts=row.prerequisite_concepts or [],
        explanation=row.explanation or "",
        examples=row.examples or [],
        common_misconceptions=row.common_misconceptions or [],
        hint_progression=row.hint_progression or [],
        quiz_questions=row.quiz_questions or [],
    )

    logger.info(
        "Loaded section %s — %s (order=%d)",
        row.section_id,
        row.title,
        row.order,
    )
