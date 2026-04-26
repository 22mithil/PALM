"""
StatePrompt Builder — converts raw Context Aggregator output into a
validated ``StatePrompt`` Pydantic model.

Acts as the boundary between the untyped aggregator dict and the
strongly-typed schema that agents consume.  Applies fallback defaults
for any missing or ``None`` fields so downstream code never needs
to handle missing data.

Usage::

    from app.state.state_prompt_builder import build_state_prompt

    raw = await context_aggregator.build(student_id, session_id, db)
    prompt = build_state_prompt(raw)          # StatePrompt (validated)
    print(prompt.emotion.label)               # "happy"

Or use the async shorthand that does both steps::

    prompt = await build_state_prompt_from_session(
        student_id, session_id, db
    )
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.state_prompt import EmotionState, StatePrompt
from app.state.context_manager import context_aggregator

logger = logging.getLogger(__name__)

# ── Defaults applied when aggregator values are None / missing ───────────

_DEFAULTS: dict[str, Any] = {
    "query": "",
    "emotion": {"label": "neutral", "confidence": 0.0},
    "gaze": "unknown",
    "current_topic": "Fractions",
    "difficulty_level": 5,
    "mastery_score": 0.0,
    "last_responses": [],
    "session_summary": None,
}


# ── Builder ──────────────────────────────────────────────────────────────


def build_state_prompt(raw: dict[str, Any]) -> StatePrompt:
    """Validate and normalise a raw Context Aggregator dict.

    Parameters
    ----------
    raw : dict
        The dict returned by ``context_aggregator.build()``.

    Returns
    -------
    StatePrompt
        Fully validated Pydantic model ready for agent consumption.

    Raises
    ------
    ValueError
        If ``student_id`` or ``session_id`` are missing (these have
        no sensible default).
    """

    if not raw.get("student_id"):
        raise ValueError("student_id is required and cannot be empty")
    if not raw.get("session_id"):
        raise ValueError("session_id is required and cannot be empty")

    # ── Apply fallback defaults for nullable / optional fields ────────
    cleaned: dict[str, Any] = {
        "student_id": raw["student_id"],
        "session_id": raw["session_id"],
    }

    for key, default in _DEFAULTS.items():
        value = raw.get(key)
        cleaned[key] = value if value is not None else default

    # ── Normalise emotion sub-object ─────────────────────────────────
    emotion_raw = cleaned["emotion"]
    if isinstance(emotion_raw, dict):
        cleaned["emotion"] = EmotionState(
            label=emotion_raw.get("label", "neutral"),
            confidence=_clamp(emotion_raw.get("confidence", 0.0), 0.0, 1.0),
        )
    elif isinstance(emotion_raw, EmotionState):
        cleaned["emotion"] = emotion_raw
    else:
        cleaned["emotion"] = EmotionState()

    # ── Clamp numeric fields to valid ranges ─────────────────────────
    cleaned["difficulty_level"] = _clamp(int(cleaned["difficulty_level"]), 1, 5)
    cleaned["mastery_score"] = _clamp(float(cleaned["mastery_score"]), 0.0, 1.0)

    # ── Truncate last_responses to max 5 ─────────────────────────────
    responses = cleaned["last_responses"]
    if isinstance(responses, list):
        cleaned["last_responses"] = responses[-5:]
    else:
        cleaned["last_responses"] = []

    prompt = StatePrompt(**cleaned)

    logger.info(
        "━━━ StatePrompt built ━━━\n%s",
        prompt.model_dump_json(indent=2),
    )

    return prompt


async def build_state_prompt_from_session(
    student_id: str,
    session_id: str,
    db: AsyncSession,
) -> StatePrompt:
    """End-to-end shorthand: aggregate context → validate → return.

    Combines the Context Aggregator and StatePrompt builder into a
    single async call for convenience.

    Parameters
    ----------
    student_id : str
        UUID string of the student.
    session_id : str
        UUID string of the current session.
    db : AsyncSession
        Active SQLAlchemy async session.

    Returns
    -------
    StatePrompt
        Validated, agent-ready context object.
    """
    raw = await context_aggregator.build(
        student_id=student_id,
        session_id=session_id,
        db=db,
    )
    return build_state_prompt(raw)


# ── Helpers ──────────────────────────────────────────────────────────────


def _clamp(value: float | int, lo: float | int, hi: float | int) -> float | int:
    """Clamp a numeric value to [lo, hi]."""
    return max(lo, min(hi, value))
