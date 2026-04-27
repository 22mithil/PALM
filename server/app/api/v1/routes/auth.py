"""
Authentication routes — register and login.

POST  /api/v1/auth/register  — Create a new student account
POST  /api/v1/auth/login     — Authenticate and receive a JWT
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth import create_access_token
from app.schemas.student import AuthResponse, StudentLogin, StudentRegister
from app.services import student_service

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new student",
)
async def register(
    payload: StudentRegister,
    db: AsyncSession = Depends(get_db),
):
    """Create a student account with email + password.

    Returns a JWT access token on success.
    Raises 409 if the email is already taken.
    """
    student = await student_service.register_student(db, payload)
    token = create_access_token(student.id)
    return AuthResponse(
        access_token=token,
        student=student,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(
    payload: StudentLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a student and return a JWT access token.

    Raises 401 if the email or password is incorrect.
    """
    student = await student_service.authenticate_student(
        db, payload.email, payload.password
    )
    # Update login streak (Issue 10)
    await student_service.update_login_streak(db, student)
    await db.commit()

    token = create_access_token(student.id)
    return AuthResponse(
        access_token=token,
        student=student,
    )
