"""
Quiz Agent — non-LLM quiz question selector.

Pulls the next unasked question from ``current_section.quiz_questions``.
Tracks asked questions via ``state.asked_questions``.
No LLM call — pure data lookup.
"""

import logging

from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)


async def run_quiz(state: TurnState) -> None:
    """Select the next unasked quiz question and write to agent_outputs.quiz."""
    if not state.current_section or not state.current_section.quiz_questions:
        logger.warning("No quiz_questions available for current section")
        state.agent_outputs.quiz = None
        return

    questions = state.current_section.quiz_questions
    asked = set(state.asked_questions)

    # Find next unasked question
    next_q = None
    for q in questions:
        q_text = q.get("question", "")
        if q_text and q_text not in asked:
            next_q = q
            break

    if next_q is None:
        # All questions exhausted
        logger.info("All quiz questions exhausted for section %s",
                     state.current_section.section_id)
        state.agent_outputs.quiz = None
        return

    question_text = next_q["question"]
    state.asked_questions.append(question_text)
    state.agent_outputs.quiz = f"[QUIZ] {question_text}"

    logger.info(
        "Quiz agent: question=%s  section=%s  asked=%d/%d",
        question_text[:50],
        state.current_section.section_id,
        len(state.asked_questions),
        len(questions),
    )
