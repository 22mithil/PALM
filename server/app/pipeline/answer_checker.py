"""
Answer Checker — LLM judge for quiz answers.

Runs before the orchestrator when the student is in quiz context
(previous turn had a non-null agent_outputs.quiz). Compares the
student's message against the current section's quiz answer and
sets ``state.last_answer_correct``.
"""

import json
import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a math answer evaluator for primary school students.
Compare the student's answer to the correct answer.
Be lenient with formatting and phrasing — focus on mathematical correctness.
Accept equivalent answers (e.g., "1/4" and "one quarter" are the same).

Respond with ONLY a JSON object (no markdown):
{"correct": true} or {"correct": false}
"""

_USER_TEMPLATE = """\
Question: {question}
Correct answer: {answer}
Student's answer: {student_answer}

Is the student's answer correct?
"""


async def check_answer(state: TurnState) -> None:
    """Check the student's answer if we're in quiz context.

    Sets ``state.last_answer_correct`` and increments ``state.attempt_count``
    when an answer is evaluated.
    """
    # Only run if previous turn had a quiz output
    if state.previous_agent_outputs_quiz is None:
        state.last_answer_correct = None
        return

    if not state.student_message.strip():
        state.last_answer_correct = None
        return

    # Find the quiz question that was asked
    if not state.current_section or not state.current_section.quiz_questions:
        state.last_answer_correct = None
        return

    # Find the most recently asked question
    asked = state.asked_questions
    if not asked:
        state.last_answer_correct = None
        return

    last_asked = asked[-1]

    # Find matching question in section data
    correct_answer = None
    question_text = ""
    for q in state.current_section.quiz_questions:
        if q.get("question") == last_asked:
            correct_answer = q.get("answer", "")
            question_text = last_asked
            break

    if correct_answer is None:
        state.last_answer_correct = None
        return

    # LLM judge
    try:
        raw = await generate_response(
            _USER_TEMPLATE.format(
                question=question_text,
                answer=correct_answer,
                student_answer=state.student_message,
            ),
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=64,
        )

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        state.last_answer_correct = bool(data.get("correct", False))
        state.attempt_count += 1

        logger.info(
            "Answer check: correct=%s (student=%s, expected=%s)",
            state.last_answer_correct,
            state.student_message[:50],
            correct_answer,
        )

    except Exception:
        logger.exception("Answer check failed — defaulting to None")
        state.last_answer_correct = None
