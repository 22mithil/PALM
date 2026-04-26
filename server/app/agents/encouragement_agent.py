"""
Encouragement Agent — LLM-based emotional support.

Called when ``emotion == frustrated`` or similar. Acknowledges
difficulty, identifies something the student did correctly.
No hints, no re-teaching.
"""

import logging

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Pal, a warm and supportive AI math tutor for primary school students.

The student is feeling {emotion}. Your ONLY job is to provide emotional support.

Rules:
- Acknowledge that math can be hard sometimes
- Find something specific they did right recently (from the conversation)
- Remind them that making mistakes is part of learning
- Do NOT give hints, answers, or re-teach anything
- Keep it under 60 words
- Use 1–2 warm emojis
- Use language appropriate for Grade {grade}\
"""


async def run_encouragement(state: TurnState) -> None:
    """Generate an encouraging message for a frustrated student."""
    try:
        recent = ""
        for msg in state.last_10_messages[-4:]:
            role = msg.get("role", "")
            content = msg.get("content", "")[:100]
            recent += f"{role}: {content}\n"

        text = await generate_response(
            f"Recent conversation:\n{recent}\n\nEncourage the student.",
            system_prompt=_SYSTEM_PROMPT.format(
                emotion=state.emotion,
                grade=state.grade,
            ),
            temperature=0.8,
            max_tokens=150,
        )
        state.agent_outputs.encouragement = text
        logger.info("Encouragement agent: generated for emotion=%s", state.emotion)
    except Exception:
        logger.exception("Encouragement agent failed")
        state.agent_outputs.encouragement = (
            "Hey, you're doing amazing! 🌟 Math can be tricky sometimes, "
            "but every mistake helps you learn. Keep going — I believe in you! 💪"
        )
