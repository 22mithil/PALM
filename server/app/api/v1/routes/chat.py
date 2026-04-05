"""
Test chat endpoint for RAG Agent testing.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents import rag_agent

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
    result = await rag_agent.run(
        req.message,
        grade=req.grade,
        topic=req.topic,
        top_k=5,
    )
    return ChatResponse(
        reply=result.answer,
        chunks_used=result.num_chunks_used,
        model=result.model,
    )
