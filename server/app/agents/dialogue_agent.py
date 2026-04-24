"""
Dialogue Agent — conversational Socratic tutor.

Generates friendly, age-appropriate responses that encourage
the student to *think* rather than passively receive answers.
Uses the student's emotional state, mastery level, and recent
conversation history to calibrate tone and complexity.

Flow:
    1. Build a dynamic system prompt tuned to grade + emotion + mastery
    2. Assemble conversation history from last_responses
    3. Call LLM via FastRouter
    4. Return AgentResponse

Usage::

    from app.agents.dialogue_agent import dialogue_agent

    response = await dialogue_agent(state_prompt)
    print(response.text)
"""

import logging
from typing import Any

from app.agents.base import BaseAgent, AgentResponse
from app.integrations.fastrouter.llm import generate_response
from app.schemas.state_prompt import StatePrompt

logger = logging.getLogger(__name__)


# ── System Prompt ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Pal, a warm and encouraging AI math tutor for primary school \
students (Grades 1–5).

## Core Principles
- **Socratic method**: Guide students with questions, never blurt out answers.
- **Warmth first**: Be kind, patient, and celebratory of effort.
- **Age-appropriate language**: Match vocabulary and sentence length to the \
student's grade level.
- **Never harsh**: No sarcasm, no criticism. Mistakes are learning opportunities.
- **Brevity**: Keep responses under 250 words unless a worked example is needed.

## Tone Rules
- Use 1–2 encouraging emojis per response (e.g. ⭐, 🎉, 💡, 🤔).
- Praise effort, not just correctness ("Great thinking!" not just "Correct!").
- When the student is wrong, say "Hmm, let's think about this together…" \
  instead of "That's wrong."
- When the student is confused, simplify and offer a concrete example.
- When the student is bored/disengaged, inject curiosity ("Did you know…?").

## Math Formatting
- Use LaTeX delimiters ($$...$$) for all math expressions.
- Show step-by-step work when helping with a problem.\
"""

# ── Emotion-aware prompt fragments ───────────────────────────────────────

_EMOTION_HINTS: dict[str, str] = {
    "happy": (
        "The student seems happy and engaged. Match their energy, "
        "keep the momentum going, and introduce slightly more challenge."
    ),
    "confused": (
        "The student appears confused. Slow down, use simpler language, "
        "provide a concrete example, and ask a single guiding question."
    ),
    "sad": (
        "The student seems sad or frustrated. Be extra gentle and "
        "encouraging. Celebrate any small progress they've made."
    ),
    "angry": (
        "The student appears frustrated or angry. Acknowledge their "
        "feelings, keep things calm, and offer to try a different approach."
    ),
    "surprised": (
        "The student seems surprised. Use this as a teaching moment — "
        "explore what surprised them and build understanding from it."
    ),
    "bored": (
        "The student appears disengaged or bored. Make the topic more "
        "interesting with a fun fact, a real-world connection, or a "
        "mini-challenge."
    ),
    "fearful": (
        "The student seems anxious. Reassure them that making mistakes "
        "is okay and part of learning. Keep the question very simple."
    ),
}


# ── Agent ────────────────────────────────────────────────────────────────


class DialogueAgent(BaseAgent):
    """Socratic dialogue agent for conversational tutoring.

    Adapts tone and complexity based on the student's emotion,
    mastery level, and grade.
    """

    name = "dialogue_agent"

    def __init__(
        self,
        *,
        temperature: float = 0.8,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    # ── BaseAgent interface ──────────────────────────────────────────

    async def run(self, state: StatePrompt) -> AgentResponse:
        """Generate a Socratic conversational response.

        Parameters
        ----------
        state : StatePrompt
            Validated context snapshot from the Context Aggregator.

        Returns
        -------
        AgentResponse
            Friendly, age-appropriate dialogue response.
        """
        query = state.query

        if not query.strip():
            return self.respond(
                text="",
                metadata={"skipped": True, "reason": "empty_query"},
            )

        # ── Build messages ───────────────────────────────────────────
        system = self._build_system_prompt(state)
        messages = self._build_messages(system, state)

        # ── Call LLM ─────────────────────────────────────────────────
        answer = await generate_response(
            query,
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        return self.respond(
            text=answer,
            metadata=self._build_metadata(state),
        )

    # ── Prompt construction ──────────────────────────────────────────

    def _build_system_prompt(self, state: StatePrompt) -> str:
        """Assemble a dynamic system prompt based on student state."""
        parts: list[str] = [SYSTEM_PROMPT]

        # Grade-level calibration
        parts.append(
            f"\n## Current Student Context\n"
            f"- Grade level: {state.difficulty_level}\n"
            f"- Topic: {state.current_topic}"
        )

        # Mastery-aware scaffolding
        if state.mastery_score < 0.3:
            parts.append(
                "- Mastery: LOW — use very simple language, "
                "break problems into tiny steps, lots of encouragement."
            )
        elif state.mastery_score < 0.7:
            parts.append(
                "- Mastery: MODERATE — student has some understanding. "
                "Use guiding questions to deepen their knowledge."
            )
        else:
            parts.append(
                "- Mastery: HIGH — student is doing well! "
                "Challenge them with extension questions or connections."
            )

        # Emotion-aware tone
        emotion_label = state.emotion.label.lower()
        if emotion_label in _EMOTION_HINTS and state.emotion.confidence > 0.4:
            parts.append(f"- Emotion guidance: {_EMOTION_HINTS[emotion_label]}")

        # Gaze awareness
        if state.gaze == "off_screen":
            parts.append(
                "- The student appears to be looking away. "
                "Re-engage them with a direct, interesting question."
            )

        return "\n".join(parts)

    @staticmethod
    def _build_messages(
        system: str,
        state: StatePrompt,
    ) -> list[dict[str, str]]:
        """Assemble the full message list for the LLM call.

        Includes conversation history from ``last_responses`` to
        maintain continuity.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
        ]

        # Inject recent conversation history as alternating turns
        for i, resp in enumerate(state.last_responses):
            # Approximate: odd = student, even = assistant
            # In practice these are all assistant responses from the rolling window
            messages.append({"role": "assistant", "content": resp})

        # Current student query
        messages.append({"role": "user", "content": state.query})

        return messages

    @staticmethod
    def _build_metadata(state: StatePrompt) -> dict[str, Any]:
        return {
            "topic": state.current_topic,
            "grade": state.difficulty_level,
            "emotion": state.emotion.label,
            "emotion_confidence": state.emotion.confidence,
            "mastery_score": state.mastery_score,
        }


# ── Singleton ────────────────────────────────────────────────────────────
dialogue_agent = DialogueAgent()
