"""
Pydantic schema for the StatePrompt — the validated, structured
context object consumed by all downstream agents.

Mirrors the output of the Context Aggregator but adds type
validation, range constraints, and safe fallback defaults so
agents never receive malformed or missing data.

Usage::

    from app.schemas.state_prompt import StatePrompt

    prompt = StatePrompt(**aggregator_output)
    print(prompt.emotion.label)       # "happy"
    print(prompt.mastery_score)       # 0.72
    print(prompt.model_dump_json())   # full JSON
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EmotionState(BaseModel):
    """Validated emotion sub-object."""

    label: str = Field(
        default="neutral",
        description="Predicted emotion label (e.g. happy, confused, bored).",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in the emotion prediction [0.0 – 1.0].",
    )


class StatePrompt(BaseModel):
    """Validated context snapshot for agent consumption.

    Every field has a safe default so construction never fails — even
    if the Context Aggregator returns partial data.

    Attributes
    ----------
    student_id : str
        UUID string of the student.
    session_id : str
        UUID string of the current session.
    query : str
        Latest student utterance (from STT transcript).
    emotion : EmotionState
        Current detected emotion with confidence.
    gaze : str
        Current gaze direction (``on_screen`` | ``off_screen`` | ``unknown``).
    current_topic : str
        Topic being discussed (e.g. ``"Fractions"``).
    difficulty_level : int
        Current difficulty tier (1 – 5).
    mastery_score : float
        Student's mastery on the current topic [0.0 – 1.0].
    last_responses : list[dict[str, str]]
        Rolling window of the last ≤ 10 dialogue turns (user + assistant).
    session_summary : str | None
        LLM-compressed summary of the session so far (may be null
        for sessions still in progress).
    """

    student_id: str = Field(
        ...,
        description="UUID string of the student.",
    )
    session_id: str = Field(
        ...,
        description="UUID string of the current session.",
    )
    query: str = Field(
        default="",
        description="Latest student utterance (STT transcript).",
    )
    emotion: EmotionState = Field(
        default_factory=EmotionState,
        description="Current detected emotion with confidence.",
    )
    gaze: str = Field(
        default="unknown",
        description="Gaze direction: on_screen | off_screen | unknown.",
    )
    current_topic: str = Field(
        default="general",
        description="Topic currently being discussed.",
    )
    difficulty_level: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Difficulty tier (1 = easiest, 5 = hardest).",
    )
    mastery_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Student mastery on the current topic [0.0 – 1.0].",
    )
    last_responses: list[dict[str, str]] = Field(
        default_factory=list,
        max_length=10,
        description="Rolling window of the last ≤ 10 message dicts (role, content).",
    )
    session_summary: Optional[str] = Field(
        default=None,
        description="LLM-compressed session summary (null if in-progress).",
    )
    consecutive_wrong: int = Field(
        default=0,
        ge=0,
        description="Count of consecutive incorrect answers (for routing).",
    )
    is_correct: Optional[bool] = Field(
        default=None,
        description="Whether the student's last answer was correct (null if no answer evaluated).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "student_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "session_id": "f0e1d2c3-b4a5-6789-0abc-def123456789",
                    "query": "I don't understand how to add fractions",
                    "emotion": {"label": "confused", "confidence": 0.85},
                    "gaze": "on_screen",
                    "current_topic": "Fractions",
                    "difficulty_level": 2,
                    "mastery_score": 0.35,
                    "last_responses": [
                        {"role": "user", "content": "What is a fraction?"},
                        {"role": "assistant", "content": "A fraction has a numerator and denominator."},
                    ],
                    "session_summary": None,
                }
            ]
        }
    }
