"""
WebSocket message schemas — Pydantic models for all WS wire-protocol
messages used across the PALM system's WebSocket endpoints.

These are *documentation* / *validation* schemas — the actual
WebSocket handlers send/receive plain dicts via ``send_json`` /
``receive_json``.  Import these models for validation where needed
or as canonical type references.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
#  TUTOR WEBSOCKET — /ws/tutor/{session_id}
# ═══════════════════════════════════════════════════════════════════════════


# ── Client → Server ──────────────────────────────────────────────────────


class TutorTriggerPayload(BaseModel):
    """Payload for a tutor trigger message."""

    student_id: str = Field(
        ..., description="UUID string of the student."
    )
    query: Optional[str] = Field(
        default=None,
        description="Explicit text query from UI. If omitted, uses latest STT transcript.",
    )


class TutorTriggerMessage(BaseModel):
    """Client → Server: request a tutor response."""

    type: str = Field(default="trigger", pattern="^trigger$")
    payload: TutorTriggerPayload


# ── Server → Client ─────────────────────────────────────────────────────


class TokenPayload(BaseModel):
    """Payload for a streamed token message."""

    token: str = Field(
        ..., description="Text token (single word or fragment)."
    )
    done: bool = Field(
        default=False,
        description="True when the stream has finished (token will be empty).",
    )


class TokenMessage(BaseModel):
    """Server → Client: one streamed token."""

    type: str = Field(default="token", pattern="^token$")
    payload: TokenPayload


class ResponseCompletePayload(BaseModel):
    """Payload for the response_complete message."""

    full_text: str = Field(
        ..., description="Complete response text."
    )
    agent_used: str = Field(
        ..., description="Name of the agent that produced the response."
    )
    mastery_delta: float = Field(
        default=0.0,
        description="Change in mastery score from this interaction.",
    )


class ResponseCompleteMessage(BaseModel):
    """Server → Client: full response summary after streaming completes."""

    type: str = Field(default="response_complete", pattern="^response_complete$")
    payload: ResponseCompletePayload


class ErrorPayload(BaseModel):
    """Payload for an error message."""

    message: str = Field(..., description="Human-readable error message.")


class ErrorMessage(BaseModel):
    """Server → Client: an error occurred."""

    type: str = Field(default="error", pattern="^error$")
    payload: ErrorPayload


# ═══════════════════════════════════════════════════════════════════════════
#  PERCEPTION WEBSOCKET — /ws/video/{session_id}
# ═══════════════════════════════════════════════════════════════════════════


class PerceptionUpdatePayload(BaseModel):
    """Payload for a perception_update message (video WS)."""

    emotion: dict[str, Any] = Field(
        ..., description='{"label": str, "confidence": float}'
    )
    gaze: str = Field(..., description="Gaze direction.")
    gaze_tracking: Optional[dict[str, Any]] = Field(
        default=None,
        description="Gaze duration tracking data.",
    )


class PerceptionUpdateMessage(BaseModel):
    """Server → Client: perception state changed."""

    type: str = Field(default="perception_update", pattern="^perception_update$")
    payload: PerceptionUpdatePayload
