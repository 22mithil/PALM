"""Add columns for issues fix: all_messages, ended_at, duration_seconds, was_completed, last_login_date

Revision ID: f8a9b2c3d4e5
Revises: bc11f2e73437
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'f8a9b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new columns for issues fix."""
    # student_sessions
    op.add_column('student_sessions', sa.Column('all_messages', JSONB, nullable=False, server_default='[]'))
    op.add_column('student_sessions', sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('student_sessions', sa.Column('duration_seconds', sa.Integer(), nullable=True))

    # student_progress
    op.add_column('student_progress', sa.Column('was_completed', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # students
    op.add_column('students', sa.Column('last_login_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove added columns."""
    op.drop_column('students', 'last_login_date')
    op.drop_column('student_progress', 'was_completed')
    op.drop_column('student_sessions', 'duration_seconds')
    op.drop_column('student_sessions', 'ended_at')
    op.drop_column('student_sessions', 'all_messages')
