"""
Quiz Agent — adaptive question generation.

Generates quiz questions calibrated to the student's mastery level
and current topic. Question type is selected automatically based on
mastery to provide appropriate challenge.

Question types:
    • **MCQ** (mastery < 0.4)     — multiple choice, lower cognitive load
    • **Fill-in** (0.4 ≤ m < 0.7) — fill-in-the-blank, recall-based
    • **Short answer** (m ≥ 0.7)  — open-ended, deeper understanding

Usage::

    from app.agents.quiz_agent import quiz_agent

    response = await quiz_agent(state_prompt)
    print(response.metadata["question_type"])  # "mcq" | "fill" | "short"
"""

import logging
from typing import Any

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)


# ── Question type resolution ─────────────────────────────────────────────

QUESTION_TYPES = ("mcq", "fill", "short")


def _resolve_question_type(mastery: float) -> str:
    """Select question type based on mastery score."""
    if mastery < 0.4:
        return "mcq"
    elif mastery < 0.7:
        return "fill"
    return "short"


# ── System prompts per question type ─────────────────────────────────────

_TYPE_PROMPTS: dict[str, str] = {
    "mcq": """\
You are Pal, a friendly AI math tutor for Grade {grade} students.

Generate a **multiple-choice question** on {topic}.

## Format (strict)
**Question:** [clear, concise question]

A) [option — one correct]
B) [option — plausible distractor]
C) [option — plausible distractor]
D) [option — plausible distractor]

**Correct Answer:** [letter]
**Explanation:** [1-sentence explanation of why the answer is correct]

## Rules
- Difficulty should match Grade {grade}, mastery {mastery:.0%}.
- Distractors must be plausible (common mistakes), not obviously wrong.
- Use LaTeX ($$...$$) for math expressions.
- Use age-appropriate, encouraging language.
- Add 1 emoji to make it fun.\
""",

    "fill": """\
You are Pal, a friendly AI math tutor for Grade {grade} students.

Generate a **fill-in-the-blank** question on {topic}.

## Format (strict)
**Complete the sentence:**
[Statement with _____ for the missing value]

**Answer:** [correct value]
**Explanation:** [1-sentence explanation]

## Rules
- Difficulty should match Grade {grade}, mastery {mastery:.0%}.
- The blank should require recall or computation, not just reading.
- Use LaTeX ($$...$$) for math expressions.
- Use age-appropriate, encouraging language.
- Add 1 emoji.\
""",

    "short": """\
You are Pal, a friendly AI math tutor for Grade {grade} students.

Generate a **short-answer question** on {topic}.

## Format (strict)
**Question:** [open-ended question requiring explanation or multi-step work]

**Expected Answer:** [concise model answer]
**Key Concepts:** [2-3 concepts the student should demonstrate]

## Rules
- Difficulty should match Grade {grade}, mastery {mastery:.0%}.
- The question should test deeper understanding, not just computation.
- Encourage the student to explain their reasoning.
- Use LaTeX ($$...$$) for math expressions.
- Use age-appropriate, encouraging language.
- Add 1 emoji.\
""",
}


# ── Difficulty calibration ───────────────────────────────────────────────

def _difficulty_label(mastery: float) -> str:
    """Human-readable difficulty for the LLM prompt."""
    if mastery < 0.2:
        return "very easy"
    elif mastery < 0.4:
        return "easy"
    elif mastery < 0.6:
        return "medium"
    elif mastery < 0.8:
        return "challenging"
    return "advanced"


# ── Agent ────────────────────────────────────────────────────────────────


class QuizAgent(BaseAgent):
    """Adaptive quiz question generator.

    Automatically selects question type (MCQ / fill / short) based
    on the student's mastery score and generates grade-appropriate
    questions on the current topic.
    """

    name = "quiz_agent"

    def __init__(
        self,
        *,
        temperature: float = 0.8,
        max_tokens: int = 768,
        model: str | None = None,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    # ── BaseAgent interface ──────────────────────────────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Generate a quiz question based on topic and mastery.

        Parameters
        ----------
        state : StatePrompt
            Validated context snapshot.

        Returns
        -------
        AgentResponse
            Quiz question with ``question_type`` in metadata.
        """
        topic = state.current_topic or "general math"
        grade = state.difficulty_level
        mastery = state.mastery_score

        # ── Resolve question type ────────────────────────────────────
        q_type = _resolve_question_type(mastery)

        # ── Build prompt ─────────────────────────────────────────────
        system = _TYPE_PROMPTS[q_type].format(
            grade=grade,
            topic=topic,
            mastery=mastery,
        )

        difficulty = _difficulty_label(mastery)

        user_msg = (
            f"Topic: {topic}\n"
            f"Grade: {grade}\n"
            f"Student mastery: {mastery:.0%}\n"
            f"Target difficulty: {difficulty}\n"
        )

        # Add emotion context for tone calibration
        if state.emotion.label not in ("neutral", "unknown"):
            user_msg += f"Student emotion: {state.emotion.label}\n"

        user_msg += f"\nGenerate a {q_type.upper()} question."

        # ── Call LLM ─────────────────────────────────────────────────
        question_text = await generate_response(
            user_msg,
            system_prompt=system,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        logger.info(
            "Quiz generated  session=%s  type=%s  topic=%s  "
            "mastery=%.2f  difficulty=%s",
            state.session_id,
            q_type,
            topic,
            mastery,
            difficulty,
        )

        return self.respond(
            text=question_text,
            metadata={
                "question_type": q_type,
                "difficulty": difficulty,
                "topic": topic,
                "grade": grade,
                "mastery_score": mastery,
            },
        )

    # ── Explicit type override ───────────────────────────────────────

    async def generate(
        self,
        state: StatePrompt,
        *,
        question_type: str | None = None,
    ) -> AgentResponse:
        """Generate a quiz with an explicit question type override.

        Parameters
        ----------
        state : StatePrompt
            Validated context.
        question_type : str, optional
            Force a specific type (``"mcq"``, ``"fill"``, ``"short"``).
            If ``None``, auto-selects based on mastery.

        Returns
        -------
        AgentResponse
        """
        if question_type and question_type in QUESTION_TYPES:
            # Temporarily override mastery to force the desired type
            original_mastery = state.mastery_score

            # Map type → mastery range that triggers it
            forced_mastery = {
                "mcq": 0.2,
                "fill": 0.5,
                "short": 0.8,
            }[question_type]

            # Create a modified state (Pydantic model_copy)
            forced_state = state.model_copy(
                update={"mastery_score": forced_mastery}
            )
            response = await self.run(forced_state)

            # Restore original mastery in metadata
            response.metadata["mastery_score"] = original_mastery
            response.metadata["type_forced"] = True
            return response

        return await self.run(state)


# ── Singleton ────────────────────────────────────────────────────────────
quiz_agent = QuizAgent()
