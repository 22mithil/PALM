"""
Hint Agent — progressive 3-tier hint system.

Provides scaffolded hints that escalate in specificity based on
how many hints the student has already received (tracked via
``last_responses``). Never gives the direct answer immediately.

Tiers:
    1. **Conceptual hint** — a nudge toward the right idea
    2. **Step-by-step guidance** — breaks the problem into steps
    3. **Worked example** — shows a similar solved problem (still
       not the exact answer)

Tier selection logic:
    - Count how many of the ``last_responses`` came from the hint
      agent (by checking for the ``[HINT]`` tag).
    - 0 prior hints → Tier 1
    - 1 prior hint  → Tier 2
    - 2+ prior hints → Tier 3

Usage::

    from app.agents.hint_agent import hint_agent

    response = await hint_agent(state_prompt)
    print(response.text)
    print(response.metadata["tier"])  # 1, 2, or 3
"""

import logging
from typing import Any

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)

# ── Hint tag used to identify hint responses in history ──────────────────
HINT_TAG = "[HINT]"

# ── Tier-specific system prompts ─────────────────────────────────────────

_TIER_PROMPTS: dict[int, str] = {
    1: """\
You are Pal, a friendly AI math tutor for primary school students (Grades 1–5).

The student is stuck and needs a **conceptual hint** (Tier 1).

## Rules
- Give a SHORT, gentle nudge that points toward the right concept.
- Do NOT reveal the method or the answer.
- Ask a leading question that connects to something the student already knows.
- Use age-appropriate language for Grade {grade}.
- Keep it under 60 words.
- Use 1 emoji to keep it friendly.
- Format math with LaTeX ($$...$$).

## Examples of good Tier 1 hints
- "Think about what happens when you split a pizza into equal parts… 🍕"
- "Remember what we said about place value? Which column is the 3 in?"
- "What if you tried drawing a picture of this problem? 🤔"

## CRITICAL
- NEVER give the answer or the steps. Only a conceptual nudge.\
""",

    2: """\
You are Pal, a friendly AI math tutor for primary school students (Grades 1–5).

The student already received a conceptual hint but is still stuck.
Give them **step-by-step guidance** (Tier 2).

## Rules
- Break the problem into 2–4 numbered steps.
- Describe WHAT to do at each step, but leave the actual computation to the student.
- Use age-appropriate language for Grade {grade}.
- Keep it under 100 words.
- Use 1–2 emojis.
- Format math with LaTeX ($$...$$).

## Examples of good Tier 2 guidance
- "Let's break this down: 1) Find a common denominator, 2) Convert each fraction, 3) Add the numerators. Try step 1 first! 💪"
- "Here's a plan: 1) Write the number in expanded form, 2) Look at the tens column. What do you get?"

## CRITICAL
- Give the STEPS but NOT the computed answers. Let the student do the work.\
""",

    3: """\
You are Pal, a friendly AI math tutor for primary school students (Grades 1–5).

The student has received two hints and is still struggling.
Give them a **worked example** (Tier 3) using a SIMILAR but DIFFERENT problem.

## Rules
- Create a problem that uses the SAME concept but DIFFERENT numbers.
- Solve it step-by-step with clear explanation.
- After the worked example, ask the student to try their original problem.
- Use age-appropriate language for Grade {grade}.
- Keep it under 150 words.
- Use 1–2 emojis.
- Format math with LaTeX ($$...$$).

## Structure
1. "Let me show you a similar problem…"
2. State the similar problem
3. Solve it step-by-step
4. "Now try yours the same way! You've got this! 🌟"

## CRITICAL
- Use DIFFERENT numbers from the student's actual problem.
- Do NOT solve the student's exact problem.\
""",
}


# ── Agent ────────────────────────────────────────────────────────────────


class HintAgent(BaseAgent):
    """Progressive hint agent with 3 escalating tiers.

    Automatically selects the appropriate tier based on how many
    hints have already been given in the current conversation.
    """

    name = "hint_agent"

    def __init__(
        self,
        *,
        temperature: float = 0.7,
        max_tokens: int = 768,
        model: str | None = None,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    # ── BaseAgent interface ──────────────────────────────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Generate a tiered hint for the student's current query.

        Parameters
        ----------
        state : StatePrompt
            Validated context snapshot.

        Returns
        -------
        AgentResponse
            Hint response with ``tier`` in metadata.
        """
        query = state.query

        if not query.strip():
            return self.respond(
                text="",
                metadata={"skipped": True, "reason": "empty_query"},
            )

        # ── Determine tier ───────────────────────────────────────────
        tier = self._resolve_tier(state.last_responses)

        # ── Build prompt ─────────────────────────────────────────────
        system = _TIER_PROMPTS[tier].format(grade=state.difficulty_level)
        user_prompt = self._build_user_prompt(state, tier)

        # ── Call LLM ─────────────────────────────────────────────────
        answer = await generate_response(
            user_prompt,
            system_prompt=system,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Tag the response so future tier detection can identify it
        tagged_answer = f"{HINT_TAG} {answer}"

        logger.info(
            "Hint agent: tier=%d  session=%s  topic=%s",
            tier,
            state.session_id,
            state.current_topic,
        )

        return self.respond(
            text=tagged_answer,
            metadata=self._build_metadata(state, tier),
        )

    # ── Tier resolution ──────────────────────────────────────────────

    @staticmethod
    def _resolve_tier(last_responses: list[dict[str, str]]) -> int:
        """Count prior hints in history to determine current tier.

        Returns 1, 2, or 3.
        """
        prior_hints = sum(
            1 for r in last_responses if r.get("role") == "assistant" and r.get("content", "").strip().startswith(HINT_TAG)
        )

        if prior_hints == 0:
            return 1
        elif prior_hints == 1:
            return 2
        else:
            return 3

    # ── Prompt construction ──────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(state: StatePrompt, tier: int) -> str:
        """Build the user-facing prompt with context."""
        parts: list[str] = []

        # Topic context
        parts.append(f"Topic: {state.current_topic}")
        parts.append(f"Grade: {state.difficulty_level}")

        # Mastery context
        if state.mastery_score > 0:
            parts.append(f"Student mastery: {state.mastery_score:.0%}")

        # Emotion context
        if state.emotion.label not in ("neutral", "unknown"):
            parts.append(f"Student emotion: {state.emotion.label}")

        # Prior hint context (so LLM doesn't repeat itself)
        prior_hints = [
            r.get("content", "") for r in state.last_responses
            if r.get("role") == "assistant" and r.get("content", "").strip().startswith(HINT_TAG)
        ]
        if prior_hints:
            parts.append(
                f"\nPrevious hints already given ({len(prior_hints)}):"
            )
            for i, h in enumerate(prior_hints, 1):
                # Strip the tag for cleaner context
                clean = h.replace(HINT_TAG, "").strip()
                parts.append(f"  Hint {i}: {clean}")
            parts.append("\nDo NOT repeat the same hints. Build on them.")

        parts.append(f"\nStudent's question: {state.query}")
        parts.append(f"\nProvide a Tier {tier} hint.")

        return "\n".join(parts)

    @staticmethod
    def _build_metadata(state: StatePrompt, tier: int) -> dict[str, Any]:
        return {
            "tier": tier,
            "topic": state.current_topic,
            "grade": state.difficulty_level,
            "mastery_score": state.mastery_score,
            "emotion": state.emotion.label,
            "prior_hints": sum(
                1 for r in state.last_responses
                if r.get("role") == "assistant" and r.get("content", "").strip().startswith(HINT_TAG)
            ),
        }


# ── Singleton ────────────────────────────────────────────────────────────
hint_agent = HintAgent()
