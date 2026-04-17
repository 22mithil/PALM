"""
Test chat endpoint for RAG Agent testing.
"""

import uuid
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.rag_agent import rag_agent
from app.schemas.state_prompt import StatePrompt

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    grade: int = Field(default=3, ge=1, le=5)
    topic: str = Field(default="Fractions")


class ChatResponse(BaseModel):
    reply: str
    chunks_used: int
    model: str


@router.post("/test", response_model=ChatResponse, summary="Test RAG chat")
async def test_chat(req: ChatRequest):
    """Quick test endpoint that calls the RAG Agent and returns the response."""
    # Build a dummy StatePrompt for the agent
    state = StatePrompt(
        student_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        query=req.message,
        difficulty_level=req.grade,
        current_topic=req.topic,
    )

    result = await rag_agent.run(state)
    
    return ChatResponse(
        reply=result.text,
        chunks_used=result.metadata.get("chunks_after_rerank", 0),
        model=rag_agent.model or "fastrouter_default",
    )
