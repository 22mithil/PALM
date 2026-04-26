"""
Pydantic schemas for Session API.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    student_id: uuid.UUID
    grade: int = Field(5, ge=1, le=5)
    chapter_id: int = Field(2, description="Chapter ID to study")


class SessionResponse(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    chapter_id: Optional[int] = None
    grade: int
    started_at: datetime
    turn_count: int = 0
    session_summary: Optional[str] = None

    model_config = {"from_attributes": True}
