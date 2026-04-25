"""
Chat endpoint for RAG Agent with conversation history.
"""

import uuid
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.rag_agent import rag_agent
from app.schemas.state_prompt import StatePrompt

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "student" or "tutor"
    text: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    grade: int = Field(default=5, ge=1, le=5)
    topic: str = Field(default="Fractions")
    history: list[ChatMessage] = Field(default_factory=list)
    student_id: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    chunks_used: int
    model: str


def _build_history_prompt(history: list[ChatMessage], current_msg: str) -> str:
    """Build a prompt that includes conversation history."""
    if not history:
        return current_msg

    lines = []
    for msg in history[-10:]:  # last 10 messages to keep context manageable
        role = "Student" if msg.role == "student" else "Tutor"
        lines.append(f"{role}: {msg.text}")

    lines.append(f"Student: {current_msg}")

    return (
        "[Conversation so far]\n"
        + "\n".join(lines)
        + "\n---\n"
        "Based on the conversation above, respond to the student's latest message. "
        "Remember what was already discussed — do not repeat questions the student "
        "already answered."
    )


@router.post("/test", response_model=ChatResponse, summary="RAG chat with history")
async def test_chat(req: ChatRequest):
    """Chat endpoint that sends conversation history to the RAG Agent."""

    query_with_history = _build_history_prompt(req.history, req.message)

    state = StatePrompt(
        student_id=req.student_id or str(uuid.uuid4()),
        session_id=req.session_id or str(uuid.uuid4()),
        query=query_with_history,
        difficulty_level=req.grade,
        current_topic=req.topic,
    )

    result = await rag_agent.run(state)

    return ChatResponse(
        reply=result.text,
        chunks_used=result.metadata.get("chunks_after_rerank", 0),
        model=rag_agent.model or "fastrouter_default",
    )
