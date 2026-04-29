"""
Mastery Agent — unconditional side-effect agent.

Runs every turn. Assesses understanding via LLM, updates
``student_progress`` in the DB. Handles section advancement
when mastery is achieved. Never writes to ``agent_outputs``.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.fastrouter.llm import generate_response
from app.models.curriculum import Chapter
from app.models.mastery import StudentProgress
from app.pipeline.state import SectionStatus, TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a mastery assessor for a primary school math tutor.

Evaluate the student's understanding of the current concept based on:
- Their recent messages and answers
- Whether their last answer was correct
- How many attempts and hints they needed

Section statuses and what they mean:
- "not_started" → student hasn't been introduced to this concept yet
- "introduced" → concept was just introduced, no assessment yet
- "in_progress" → student is actively working on this concept
- "struggling" → student has had multiple wrong answers or needed many hints
- "mastered" → student demonstrated solid understanding

Respond with ONLY a JSON object (no markdown):
{
  "new_status": "introduced|in_progress|struggling|mastered",
  "should_advance": false,
  "reasoning": "brief explanation"
}

Rules:
- Move to "introduced" after the concept is first explained
- Move to "in_progress" after student engages with questions
- Move to "struggling" if attempt_count >= 3 and last answers wrong, or hint_count >= 2
- Move to "mastered" only if student answered correctly with minimal hints
- Set should_advance=true ONLY when status is "mastered"
- Never skip statuses (not_started → mastered is not allowed)\
"""

_USER_TEMPLATE = """\
Concept: {concept} — {title}
Current status: {current_status}
Last answer correct: {last_answer}
Attempt count: {attempt_count}
Hint count: {hint_count}
Turn count: {turn_count}

Recent conversation:
{recent_messages}

Assess the student's mastery and determine the new status.\
"""


async def run_mastery(state: TurnState, db: AsyncSession) -> None:
    """Assess mastery and update student_progress in the DB."""
    if not state.chapter_progress or not state.current_section:
        logger.info("Mastery agent: no progress/section — skipping")
        return

    section_id = state.current_section.section_id
    current_ss = state.chapter_progress.section_statuses.get(section_id)
    current_status = current_ss.status if current_ss else "not_started"

    # Format recent messages
    recent = ""
    for msg in state.last_10_messages[-6:]:
        role = msg.get("role", "?")
        content = msg.get("content", "")[:150]
        recent += f"  {role}: {content}\n"
    if not recent:
        recent = "  (no messages yet)"

    last_answer = (
        str(state.last_answer_correct)
        if state.last_answer_correct is not None
        else "N/A"
    )

    try:
        raw = await generate_response(
            _USER_TEMPLATE.format(
                concept=state.current_section.concept,
                title=state.current_section.title,
                current_status=current_status,
                last_answer=last_answer,
                attempt_count=state.attempt_count,
                hint_count=state.hint_count,
                turn_count=state.turn_count,
                recent_messages=recent,
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=128,
        )

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        new_status = data.get("new_status", current_status)
        should_advance = data.get("should_advance", False)

        # Validate status transition
        valid_statuses = {"not_started", "introduced", "in_progress", "struggling", "mastered"}
        if new_status not in valid_statuses:
            new_status = current_status

        # Update section status in state
        state.chapter_progress.section_statuses[section_id] = SectionStatus(
            status=new_status
        )

        logger.info(
            "Mastery: %s → %s  advance=%s  section=%s",
            current_status,
            new_status,
            should_advance,
            section_id,
        )

        # Handle section advancement
        if should_advance and new_status == "mastered":
            await _advance_section(state, db)

        # Recompute completion
        _recompute_completion(state)

    except Exception:
        logger.exception("Mastery agent LLM failed — keeping current status")


async def _advance_section(state: TurnState, db: AsyncSession) -> None:
    """Advance to the next section in the chapter."""
    if not state.chapter_progress:
        return

    chapter_id = state.chapter_progress.chapter_id

    # Fetch chapter to get section order
    result = await db.execute(
        select(Chapter).where(Chapter.chapter_id == chapter_id)
    )
    chapter = result.scalars().first()
    if not chapter or not chapter.section_ids:
        return

    section_ids = chapter.section_ids
    current_idx = -1
    for i, sid in enumerate(section_ids):
        if sid == state.chapter_progress.current_section_id:
            current_idx = i
            break

    if current_idx < 0 or current_idx >= len(section_ids) - 1:
        logger.info("Already at last section — chapter complete!")
        return

    next_section_id = section_ids[current_idx + 1]
    state.chapter_progress.current_section_id = next_section_id

    # Ensure next section has a status entry
    if next_section_id not in state.chapter_progress.section_statuses:
        state.chapter_progress.section_statuses[next_section_id] = SectionStatus(
            status="not_started"
        )

    # Reset counters for the new section
    state.hint_count = 0
    state.attempt_count = 0
    state.asked_questions = []

    logger.info(
        "Advanced to section %s (index %d/%d)",
        next_section_id,
        current_idx + 2,
        len(section_ids),
    )


def _recompute_completion(state: TurnState) -> None:
    """Recompute completion_percent from section statuses."""
    if not state.chapter_progress:
        return

    statuses = state.chapter_progress.section_statuses
    if not statuses:
        return

    # If chapter was already completed, mastery score is locked at 100%
    if state.chapter_progress.was_completed:
        state.chapter_progress.completion_percent = 100.0
        return

    total = len(statuses)
    mastered = sum(
        1 for ss in statuses.values() if ss.status == "mastered"
    )
    state.chapter_progress.completion_percent = round(
        (mastered / total) * 100, 1
    ) if total > 0 else 0.0

    if state.chapter_progress.completion_percent >= 100.0:
        state.chapter_progress.was_completed = True
