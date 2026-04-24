"""
Mastery Agent — adaptive difficulty and mastery tracking.

Evaluates the student's correctness, adjusts their mastery score
in the DB, and recommends difficulty/topic changes based on
performance trends.

Modes:
    • **Remedial** (mastery < 0.3)  — lower difficulty, encourage basics
    • **Building**  (0.3 ≤ mastery < 0.7) — steady scaffolding
    • **Advance**   (mastery ≥ 0.7) — increase difficulty, suggest new topics

Flow:
    1. Receive StatePrompt + correctness signal
    2. Compute mastery delta based on correctness + current score
    3. Update mastery_scores in DB via mastery_service
    4. Generate coaching text via LLM
    5. Return AgentResponse with mastery_delta in metadata

Usage::

    from app.agents.mastery_agent import mastery_agent

    # Standard run (coaching only, no DB update)
    response = await mastery_agent(state_prompt)

    # Full assessment with DB update
    response = await mastery_agent.assess(
        state_prompt, correctness=True, db=async_session
    )
    print(response.metadata["mastery_delta"])  # 0.05
"""

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt
from app.services.mastery_service import adjust_mastery

logger = logging.getLogger(__name__)


# ── Mastery delta tuning ─────────────────────────────────────────────────

# How much mastery changes per correct/incorrect response.
# Smaller gains at high mastery (diminishing returns), larger
# recovery at low mastery (encouragement).

_DELTA_TABLE: dict[str, dict[str, float]] = {
    "correct": {
        "low":  0.08,    # mastery < 0.3
        "mid":  0.05,    # 0.3 ≤ mastery < 0.7
        "high": 0.03,    # mastery ≥ 0.7
    },
    "incorrect": {
        "low":  -0.03,   # gentle penalty when already struggling
        "mid":  -0.05,
        "high": -0.07,   # steeper drop to prevent false confidence
    },
}


def _mastery_band(score: float) -> str:
    if score < 0.3:
        return "low"
    elif score < 0.7:
        return "mid"
    return "high"


def _compute_delta(score: float, correct: bool) -> float:
    """Compute mastery score delta based on current score + correctness."""
    band = _mastery_band(score)
    key = "correct" if correct else "incorrect"
    return _DELTA_TABLE[key][band]


# ── System prompts per mode ──────────────────────────────────────────────

_MODE_PROMPTS: dict[str, str] = {
    "remedial": """\
You are Pal, an encouraging AI math tutor. The student is struggling \
(mastery: {mastery:.0%}) on {topic}.

## Your role
- Acknowledge their effort warmly.
- Suggest going back to foundational concepts.
- Recommend lowering the difficulty level.
- Give ONE specific, achievable next step.
- Keep it under 80 words. Use 1 encouraging emoji.

Current difficulty: {difficulty}/5
The student just answered {"correctly" if {correct} else "incorrectly"}.\
""",

    "building": """\
You are Pal, an encouraging AI math tutor. The student is making progress \
(mastery: {mastery:.0%}) on {topic}.

## Your role
- Celebrate their progress.
- Reinforce what they're doing right.
- Suggest the next concept to practice.
- Keep current difficulty or nudge up slightly.
- Keep it under 80 words. Use 1 emoji.

Current difficulty: {difficulty}/5
The student just answered {"correctly" if {correct} else "incorrectly"}.\
""",

    "advance": """\
You are Pal, an encouraging AI math tutor. The student is doing great \
(mastery: {mastery:.0%}) on {topic}!

## Your role
- Celebrate their achievement enthusiastically.
- Suggest moving to a harder difficulty or a new related topic.
- Pose an extension challenge or real-world connection.
- Keep it under 80 words. Use 1–2 emojis.

Current difficulty: {difficulty}/5
The student just answered {"correctly" if {correct} else "incorrectly"}.\
""",
}


# ── Agent ────────────────────────────────────────────────────────────────


class MasteryAgent(BaseAgent):
    """Adaptive mastery tracking and difficulty recommendation agent.

    Two modes of operation:

    1. ``run(state)`` — lightweight coaching text based on current
       mastery, no DB writes (used by the Orchestrator in the
       standard pipeline).

    2. ``assess(state, correctness, db)`` — full assessment: computes
       mastery delta, persists to DB, and returns coaching with the
       delta in metadata.
    """

    name = "mastery_agent"

    def __init__(
        self,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        model: str | None = None,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    # ── BaseAgent interface (coaching only, no DB) ───────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Generate mastery-aware coaching text (no DB update).

        Used in the standard agent pipeline. For full assessment
        with DB persistence, use :meth:`assess`.
        """
        mode = self._resolve_mode(state.mastery_score)

        coaching = await self._generate_coaching(
            state=state,
            mode=mode,
            correct=None,  # unknown in passive mode
        )

        return self.respond(
            text=coaching,
            metadata={
                "mode": mode,
                "mastery_score": state.mastery_score,
                "mastery_delta": 0.0,
                "suggested_difficulty": self._suggest_difficulty(
                    state.mastery_score, state.difficulty_level
                ),
                "topic": state.current_topic,
            },
        )

    # ── Full assessment with DB update ───────────────────────────────

    async def assess(
        self,
        state: StatePrompt,
        *,
        correctness: bool,
        db: AsyncSession,
    ) -> AgentResponse:
        """Evaluate correctness, update DB mastery, and return coaching.

        Parameters
        ----------
        state : StatePrompt
            Current session context.
        correctness : bool
            Whether the student's last answer was correct.
        db : AsyncSession
            Active DB session for mastery persistence.

        Returns
        -------
        AgentResponse
            Coaching text with ``mastery_delta``, ``new_score``,
            and ``suggested_difficulty`` in metadata.
        """
        current_score = state.mastery_score
        delta = _compute_delta(current_score, correctness)
        mode = self._resolve_mode(current_score)

        # ── Persist to DB ────────────────────────────────────────────
        student_uuid = uuid.UUID(state.student_id)
        topic = state.current_topic or "general"
        grade = state.difficulty_level

        try:
            mastery_row, actual_delta = await adjust_mastery(
                db=db,
                student_id=student_uuid,
                topic=topic,
                grade=grade,
                delta=delta,
            )
            new_score = mastery_row.score
        except Exception:
            logger.exception(
                "Failed to update mastery  student=%s  topic=%s",
                state.student_id,
                topic,
            )
            new_score = max(0.0, min(1.0, current_score + delta))
            actual_delta = delta

        # ── Generate coaching ────────────────────────────────────────
        coaching = await self._generate_coaching(
            state=state,
            mode=mode,
            correct=correctness,
        )

        suggested_difficulty = self._suggest_difficulty(
            new_score, state.difficulty_level
        )

        logger.info(
            "Mastery assessed  student=%s  topic=%s  "
            "correct=%s  delta=%.3f  new_score=%.3f  mode=%s",
            state.student_id,
            topic,
            correctness,
            actual_delta,
            new_score,
            mode,
        )

        return self.respond(
            text=coaching,
            metadata={
                "mode": mode,
                "correct": correctness,
                "mastery_score": new_score,
                "mastery_delta": round(actual_delta, 4),
                "previous_score": current_score,
                "suggested_difficulty": suggested_difficulty,
                "topic": state.current_topic,
            },
        )

    # ── Mode resolution ──────────────────────────────────────────────

    @staticmethod
    def _resolve_mode(mastery_score: float) -> str:
        band = _mastery_band(mastery_score)
        return {
            "low": "remedial",
            "mid": "building",
            "high": "advance",
        }[band]

    # ── Difficulty suggestion ────────────────────────────────────────

    @staticmethod
    def _suggest_difficulty(mastery_score: float, current: int) -> int:
        """Suggest a new difficulty level based on mastery.

        Rules:
            - mastery < 0.2 and current > 1 → decrease by 1
            - mastery ≥ 0.8 and current < 5 → increase by 1
            - otherwise → keep current
        """
        if mastery_score < 0.2 and current > 1:
            return current - 1
        if mastery_score >= 0.8 and current < 5:
            return current + 1
        return current

    # ── LLM coaching generation ──────────────────────────────────────

    async def _generate_coaching(
        self,
        state: StatePrompt,
        mode: str,
        correct: Optional[bool],
    ) -> str:
        """Build and call LLM for mode-specific coaching text."""

        # Build a clean system prompt (avoid f-string-in-f-string issues)
        correctness_str = (
            "correctly" if correct
            else "incorrectly" if correct is False
            else "— correctness unknown"
        )

        system = (
            f"You are Pal, an encouraging AI math tutor for Grades 1–5.\n\n"
            f"Mode: {mode.upper()}\n"
            f"Student mastery on {state.current_topic}: {state.mastery_score:.0%}\n"
            f"Current difficulty: {state.difficulty_level}/5\n"
            f"The student just answered {correctness_str}.\n\n"
        )

        if mode == "remedial":
            system += (
                "Your role:\n"
                "- Acknowledge their effort warmly.\n"
                "- Suggest revisiting foundational concepts.\n"
                "- Recommend lowering the difficulty.\n"
                "- Give ONE specific, achievable next step.\n"
                "- Keep it under 80 words. Use 1 encouraging emoji."
            )
        elif mode == "building":
            system += (
                "Your role:\n"
                "- Celebrate their progress.\n"
                "- Reinforce what they're doing right.\n"
                "- Suggest the next concept to practice.\n"
                "- Keep current difficulty or nudge up slightly.\n"
                "- Keep it under 80 words. Use 1 emoji."
            )
        else:  # advance
            system += (
                "Your role:\n"
                "- Celebrate their achievement enthusiastically.\n"
                "- Suggest a harder difficulty or a new related topic.\n"
                "- Pose an extension challenge or real-world connection.\n"
                "- Keep it under 80 words. Use 1–2 emojis."
            )

        user_msg = (
            f"Topic: {state.current_topic}\n"
            f"Student's last query: {state.query or '(none)'}\n"
            f"Provide a brief coaching message."
        )

        return await generate_response(
            user_msg,
            system_prompt=system,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


# ── Singleton ────────────────────────────────────────────────────────────
mastery_agent = MasteryAgent()
