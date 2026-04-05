"""
Pydantic schemas for Student API.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────────────────────────

class StudentCreate(BaseModel):
    """POST /api/v1/students — request body."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Riya"])
    grade: int = Field(..., ge=1, le=5, description="Grade level (1–5)")
    age: Optional[int] = Field(None, ge=4, le=15)


class StudentUpdate(BaseModel):
    """PUT /api/v1/students/{id} — request body.

    All fields optional so the client can send partial updates.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    grade: Optional[int] = Field(None, ge=1, le=5)
    age: Optional[int] = Field(None, ge=4, le=15)


# ── Response Schemas ─────────────────────────────────────────────────────

class StudentResponse(BaseModel):
    """Standard student response returned by all student endpoints."""

    id: uuid.UUID
    name: str
    grade: int
    age: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
