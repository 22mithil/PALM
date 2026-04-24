"""
Engagement Agent — re-engagement through fun math content.

Activates when the student shows signs of disengagement (bored
emotion, off-screen gaze, or prolonged inactivity) and generates
a fun math riddle, puzzle, or mini-challenge to recapture attention.

Trigger conditions (any one is sufficient):
    • emotion = "bored" with confidence > 0.4
    • gaze = "off_screen"
    • emotion = "sad" / "fearful" (disengagement variants)

When none of the triggers fire, the agent returns a no-op response
with ``triggered: false`` so the Orchestrator can skip it.

Usage::

    from app.agents.engagement_agent import engagement_agent

    response = await engagement_agent(state_prompt)
    if response.metadata.get("triggered"):
        # show engagement card to student
        send_to_frontend(response.text, type="engagement_card")
"""

import logging
import random
from typing import Any

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)


# ── Engagement content types ─────────────────────────────────────────────

CONTENT_TYPES = ["riddle", "mini_challenge", "fun_fact", "puzzle"]

# ── System prompts per content type ──────────────────────────────────────

_CONTENT_PROMPTS: dict[str, str] = {
    "riddle": """\
You are Pal, a fun AI math tutor for Grade {grade} students.

Generate a SHORT, entertaining math riddle related to {topic}.
- The riddle should be solvable by a Grade {grade} student.
- Make it playful and intriguing — use a story or character.
- End with "Can you figure it out?" or similar.
- Keep it under 80 words.
- Use 1–2 fun emojis.
- Format any math with LaTeX ($$...$$).\
""",

    "mini_challenge": """\
You are Pal, a fun AI math tutor for Grade {grade} students.

Create a QUICK mini-challenge about {topic}.
- Frame it as a fun dare or speed challenge ("Can you solve this in 30 seconds?").
- The problem should be slightly easier than their current level to build confidence.
- Keep it under 60 words.
- Use energetic language and 1–2 emojis.
- Format any math with LaTeX ($$...$$).\
""",

    "fun_fact": """\
You are Pal, a fun AI math tutor for Grade {grade} students.

Share a MIND-BLOWING math fun fact related to {topic}.
- Connect it to something a kid would find cool (sports, games, animals, space).
- End with a simple question that makes them curious to learn more.
- Keep it under 80 words.
- Use 1–2 emojis.
- Use age-appropriate language.\
""",

    "puzzle": """\
You are Pal, a fun AI math tutor for Grade {grade} students.

Create a visual or logical math puzzle related to {topic}.
- Use a pattern, sequence, or "what comes next?" format.
- Make it feel like a game, not homework.
- Keep it under 80 words.
- Use 1–2 emojis.
- Format any math with LaTeX ($$...$$).\
""",
}

# ── Disengagement emotions ───────────────────────────────────────────────

_DISENGAGED_EMOTIONS = frozenset({"bored", "sad", "fearful", "disgust"})
_EMOTION_CONFIDENCE_THRESHOLD = 0.4


# ── Agent ────────────────────────────────────────────────────────────────


class EngagementAgent(BaseAgent):
    """Re-engagement agent that generates fun math content.

    Only fires when disengagement signals are detected. Returns
    a no-op ``AgentResponse`` (``triggered: false``) when the
    student appears engaged.
    """

    name = "engagement_agent"

    def __init__(
        self,
        *,
        temperature: float = 0.9,
        max_tokens: int = 512,
        model: str | None = None,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    # ── BaseAgent interface ──────────────────────────────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Check for disengagement and generate re-engagement content.

        Returns a no-op response if no triggers are detected.
        """
        trigger = self._detect_trigger(state)

        if trigger is None:
            return self.respond(
                text="",
                metadata={"triggered": False, "reason": "student_engaged"},
            )

        # ── Pick a random content type ───────────────────────────────
        content_type = random.choice(CONTENT_TYPES)

        # ── Generate content ─────────────────────────────────────────
        system = _CONTENT_PROMPTS[content_type].format(
            grade=state.difficulty_level,
            topic=state.current_topic or "math",
        )

        user_msg = (
            f"The student seems {trigger}. "
            f"Generate a {content_type.replace('_', ' ')} to re-engage them.\n"
            f"Topic: {state.current_topic or 'general math'}\n"
            f"Grade: {state.difficulty_level}"
        )

        text = await generate_response(
            user_msg,
            system_prompt=system,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        logger.info(
            "Engagement triggered  session=%s  trigger=%s  type=%s",
            state.session_id,
            trigger,
            content_type,
        )

        return self.respond(
            text=text,
            metadata={
                "triggered": True,
                "trigger": trigger,
                "type": "engagement_card",
                "content_type": content_type,
                "topic": state.current_topic,
                "grade": state.difficulty_level,
            },
        )

    # ── Trigger detection ────────────────────────────────────────────

    @staticmethod
    def _detect_trigger(state: StatePrompt) -> str | None:
        """Detect disengagement signals from the StatePrompt.

        Returns a human-readable trigger reason, or ``None`` if
        the student appears engaged.

        Priority order:
            1. Off-screen gaze (strongest signal)
            2. Disengaged emotion with sufficient confidence
        """
        # Gaze-based trigger
        if state.gaze == "off_screen":
            return "looking away"

        # Emotion-based trigger
        emotion = state.emotion.label.lower()
        if (
            emotion in _DISENGAGED_EMOTIONS
            and state.emotion.confidence > _EMOTION_CONFIDENCE_THRESHOLD
        ):
            return emotion

        return None


# ── Singleton ────────────────────────────────────────────────────────────
engagement_agent = EngagementAgent()
