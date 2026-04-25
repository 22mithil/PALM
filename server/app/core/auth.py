"""
JWT authentication utilities.

Provides token creation / decoding and a FastAPI dependency
``get_current_student`` that validates the ``Authorization: Bearer``
header and returns the authenticated ``Student`` row.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.api.deps import get_db
from app.models.student import Student

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Token helpers ────────────────────────────────────────────────────────


def create_access_token(
    student_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT containing the student's UUID."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(student_id),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Decode a JWT and return the ``sub`` (student_id) claim.

    Returns ``None`` on any error (expired, tampered, malformed).
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


# ── FastAPI dependency ───────────────────────────────────────────────────


async def get_current_student(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Student:
    """Validate the bearer token and return the authenticated student.

    Raises 401 if the token is missing, invalid, or the student no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    student_id = decode_access_token(token)
    if student_id is None:
        raise credentials_exception

    try:
        result = await db.execute(
            select(Student).where(Student.id == uuid.UUID(student_id))
        )
        student = result.scalars().first()
    except Exception:
        raise credentials_exception

    if student is None:
        raise credentials_exception

    return student
