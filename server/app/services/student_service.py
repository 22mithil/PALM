"""
Student service layer — all DB operations for students.
"""

import logging
import uuid

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Student
from app.schemas.student import StudentCreate, StudentRegister, StudentUpdate

logger = logging.getLogger(__name__)


# ── Password helpers ─────────────────────────────────────────────────────


def _hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── CRUD ─────────────────────────────────────────────────────────────────


async def create_student(db: AsyncSession, payload: StudentCreate) -> Student:
    """Insert a new student and return the created row (legacy, no auth)."""
    student = Student(
        name=payload.name,
        email=f"{payload.name.lower().replace(' ', '_')}@palm.local",
        password_hash=_hash_password("default_password"),
        grade=payload.grade,
        age=payload.age,
    )
    db.add(student)
    await db.flush()          # populate server-generated fields (id, timestamps)
    await db.refresh(student)
    return student


async def register_student(db: AsyncSession, payload: StudentRegister) -> Student:
    """Register a new student with email and hashed password.

    Raises 409 if the email is already taken.
    """
    # Check for duplicate email
    existing = await db.execute(
        select(Student).where(Student.email == payload.email)
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this email already exists",
        )

    student = Student(
        name=payload.name,
        email=payload.email,
        password_hash=_hash_password(payload.password),
        grade=payload.grade,
        age=payload.age,
    )
    db.add(student)
    await db.flush()
    await db.refresh(student)
    logger.info("Registered student  id=%s  email=%s", student.id, student.email)
    return student


async def authenticate_student(
    db: AsyncSession,
    email: str,
    password: str,
) -> Student:
    """Verify email + password. Returns the student or raises 401."""
    result = await db.execute(select(Student).where(Student.email == email))
    student = result.scalars().first()

    if student is None or not _verify_password(password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.info("Authenticated student  id=%s  email=%s", student.id, student.email)
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


async def update_login_streak(db: AsyncSession, student: Student) -> None:
    """Update the student's daily login streak.

    - If last login was yesterday → streak += 1
    - If last login was today → no change
    - If last login was >1 day ago or None → streak = 1
    """
    from datetime import date, timezone

    today = date.today()
    last_login = student.last_login_date

    if last_login is not None:
        last_date = last_login.date() if hasattr(last_login, 'date') else last_login
        diff = (today - last_date).days
        if diff == 0:
            # Already logged in today — no change
            return
        elif diff == 1:
            student.streak = (student.streak or 0) + 1
        else:
            student.streak = 1
    else:
        student.streak = 1

    from datetime import datetime
    student.last_login_date = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(student)
    logger.info("Updated streak for student %s to %d", student.id, student.streak)

