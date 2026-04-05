"""
Session API routes.

POST   /api/v1/sessions              — Start a new learning session
GET    /api/v1/sessions/{id}         — Get session details
PATCH  /api/v1/sessions/{id}/end     — End and summarize a session
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.session import SessionCreate, SessionEnd, SessionResponse
from app.services import session_service

router = APIRouter()


@router.post(
    "/",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new learning session",
)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start a new tutoring session for a student.

    Creates a session row with ``difficulty_level = 1`` (easiest).
    Validates that the referenced student exists.
    """
    session = await session_service.create_session(db, payload)
    return session


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get session details",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a session by its UUID. Returns 404 if not found."""
    session = await session_service.get_session_by_id(db, session_id)
    return session


@router.patch(
    "/{session_id}/end",
    response_model=SessionResponse,
    summary="End and summarize a session",
)
async def end_session(
    session_id: uuid.UUID,
    payload: Optional[SessionEnd] = Body(None),
    db: AsyncSession = Depends(get_db),
):
    """End an active session.

    Sets ``ended_at`` to the current timestamp and optionally stores
    an LLM-generated session summary. Returns 409 if the session
    has already ended.
    """
    session = await session_service.end_session(db, session_id, payload)
    return session
