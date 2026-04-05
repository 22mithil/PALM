"""
Student service layer — all DB operations for students.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.schemas.student import StudentCreate, StudentUpdate


async def create_student(db: AsyncSession, payload: StudentCreate) -> Student:
    """Insert a new student and return the created row."""
    student = Student(
        name=payload.name,
        grade=payload.grade,
        age=payload.age,
    )
    db.add(student)
    await db.flush()          # populate server-generated fields (id, timestamps)
    await db.refresh(student)
    return student


async def get_student_by_id(db: AsyncSession, student_id: uuid.UUID) -> Student:
    """Fetch a single student by UUID. Raises 404 if not found."""
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalars().first()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student {student_id} not found",
        )
    return student


async def update_student(
    db: AsyncSession,
    student_id: uuid.UUID,
    payload: StudentUpdate,
) -> Student:
    """Update an existing student with the provided fields."""
    student = await get_student_by_id(db, student_id)

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field, value in update_data.items():
        setattr(student, field, value)

    await db.flush()
    await db.refresh(student)
    return student
