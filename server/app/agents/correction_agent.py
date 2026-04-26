"""
Correction Agent — LLM-based wrong-answer correction.

Called when ``last_answer_correct == False``. Uses the section's
``common_misconceptions`` to identify the likely error and address
the specific mistake. Must not give the answer or re-teach.
"""

import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Pal, a friendly AI math tutor for primary school students (Grades 1–5).

The student just gave a wrong answer. Your job is to:
1. Acknowledge their effort positively
2. Point out the specific mistake WITHOUT giving the correct answer
3. Use the common misconceptions below to identify what went wrong
4. Guide them to try again

Rules:
- Do NOT reveal the correct answer
- Do NOT re-teach the entire concept
- Keep it under 80 words
- Use warm, encouraging language appropriate for Grade {grade}
- Use 1 emoji\
"""

_USER_TEMPLATE = """\
Section: {title} — {concept}
Common misconceptions:
{misconceptions}

The student's wrong answer: {student_answer}
The question was: {question}

Address their specific mistake and encourage them to try again.\
"""


async def run_correction(state: TurnState) -> None:
    """Generate a correction for a wrong answer."""
    if state.last_answer_correct is not False:
        return

    misconceptions = ""
    question = ""
    if state.current_section:
        misconceptions = "\n".join(
            f"- {m}" for m in state.current_section.common_misconceptions
        ) or "- (none available)"

    # Find the question that was asked
    if state.asked_questions and state.current_section:
        last_asked = state.asked_questions[-1]
        for q in state.current_section.quiz_questions:
            if q.get("question") == last_asked:
                question = last_asked
                break

    try:
        text = await generate_response(
            _USER_TEMPLATE.format(
                title=state.current_section.title if state.current_section else "",
                concept=state.current_section.concept if state.current_section else "",
                misconceptions=misconceptions,
                student_answer=state.student_message,
                question=question,
            ),
            system_prompt=_SYSTEM_PROMPT.format(grade=state.grade),
            temperature=0.7,
            max_tokens=256,
        )
        state.agent_outputs.correction = text
        logger.info("Correction agent: generated response")
    except Exception:
        logger.exception("Correction agent failed")
        state.agent_outputs.correction = (
            "That's not quite right, but great try! 🌟 "
            "Look at the question again carefully and give it another shot."
        )
