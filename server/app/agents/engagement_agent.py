"""
Engagement Agent — LLM-based re-engagement.

Called when gaze guardrail triggers (consecutive_gaze_away >= 2)
or orchestrator detects disengagement. Generates a fun, attention-
grabbing prompt related to the current section's concept.
"""

import logging
import random

from app.integrations.fastrouter.llm import generate_response
from app.pipeline.state import TurnState

logger = logging.getLogger(__name__)

_CONTENT_TYPES = ["riddle", "fun_fact", "mini_challenge"]

_SYSTEM_PROMPT = """\
You are Pal, a fun AI math tutor for Grade {grade} students.

The student seems distracted. Generate a SHORT, attention-grabbing {content_type} \
related to {concept} to re-engage them.

Rules:
- Make it playful and intriguing
- Keep it under 60 words
- Use 1–2 fun emojis
- End with a question to draw them back in
- Use age-appropriate language\
"""


async def run_engagement(state: TurnState) -> None:
    """Generate a re-engagement prompt."""
    concept = "math"
    if state.current_section:
        concept = state.current_section.title or state.current_section.concept

    content_type = random.choice(_CONTENT_TYPES)

    try:
        text = await generate_response(
            f"Re-engage the student who is distracted. Topic: {concept}",
            system_prompt=_SYSTEM_PROMPT.format(
                grade=state.grade,
                content_type=content_type,
                concept=concept,
            ),
            temperature=0.9,
            max_tokens=150,
        )
        state.agent_outputs.engagement = text
        logger.info("Engagement agent: type=%s concept=%s", content_type, concept)
    except Exception:
        logger.exception("Engagement agent failed")
        state.agent_outputs.engagement = (
            "Hey! 👋 I have a quick math puzzle for you — "
            "are you ready? Let's see how fast you can solve it! 🚀"
        )
