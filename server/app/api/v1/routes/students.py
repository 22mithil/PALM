"""
Student API routes.

POST   /api/v1/students          — Register new student
GET    /api/v1/students/{id}     — Get student profile
PUT    /api/v1/students/{id}     — Update student profile
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate
from app.services import student_service

router = APIRouter()


@router.post(
    "/",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new student",
)
async def create_student(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new student profile.

    Accepts name (required), grade 1–5 (required), and an optional age.
    Returns the created student with a server-generated UUID.
    """
    student = await student_service.create_student(db, payload)
    return student


@router.get(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Get student profile",
)
async def get_student(
    student_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a student by their UUID. Returns 404 if not found."""
    student = await student_service.get_student_by_id(db, student_id)
    return student


@router.put(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Update student profile",
)
async def update_student(
    student_id: uuid.UUID,
    payload: StudentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing student profile (partial updates allowed)."""
    student = await student_service.update_student(db, student_id, payload)
    return student
