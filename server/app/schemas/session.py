"""
Pydantic schemas for Session API.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    """POST /api/v1/sessions — request body."""

    student_id: uuid.UUID
    grade: int = Field(..., ge=1, le=5)
    topic: Optional[str] = Field(None, max_length=100, examples=["Fractions"])


class SessionEnd(BaseModel):
    """PATCH /api/v1/sessions/{id}/end — optional request body."""

    summary: Optional[str] = Field(
        None,
        description="LLM-compressed session summary. If omitted, a placeholder is generated.",
    )
    duration_seconds: Optional[int] = None
    performance_result: Optional[str] = None
    mastery_score: Optional[int] = None


# ── Response Schemas ─────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    """Standard session response."""

    id: uuid.UUID
    student_id: uuid.UUID
    grade: int
    topic: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    total_turns: int
    duration_seconds: Optional[int] = None
    performance_result: Optional[str] = None
    mastery_score: Optional[int] = None

    model_config = {"from_attributes": True}
