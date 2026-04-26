"""
Chat endpoint — simple test endpoint for the pipeline.

Replaces the old RAG chat endpoint.
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.db.session import async_session_factory
from app.pipeline.runner import run_turn_pipeline

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    grade: int = Field(default=5, ge=1, le=5)
    topic: str = Field(default="Fractions")
    student_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str


@router.post("/test", response_model=ChatResponse, summary="Test chat endpoint")
async def test_chat(req: ChatRequest):
    """Simple test endpoint that runs the pipeline for a single turn."""
    student_id = req.student_id or str(uuid.uuid4())
    session_id = req.session_id or str(uuid.uuid4())

    async with async_session_factory() as db:
        result = await run_turn_pipeline(
            student_id=student_id,
            session_id=session_id,
            student_message=req.message,
            db=db,
        )
        await db.commit()

    return ChatResponse(reply=result)
