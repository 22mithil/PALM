"""add_auth_fields

Revision ID: 5768394baee2
Revises: 780c678c3200
Create Date: 2026-04-25 15:18:20.740178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5768394baee2'
down_revision: Union[str, Sequence[str], None] = '780c678c3200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add email and password_hash columns to students table."""
    # Add email column (nullable first to backfill existing rows)
    op.add_column('students', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('students', sa.Column('password_hash', sa.String(255), nullable=True))

    # Backfill existing rows with generated email and default password hash
    op.execute(
        "UPDATE students SET email = CONCAT(LOWER(REPLACE(name, ' ', '_')), '_', id::text, '@palm.local') WHERE email IS NULL"
    )
    op.execute(
        "UPDATE students SET password_hash = 'migrated_no_password' WHERE password_hash IS NULL"
    )

    # Now make columns non-nullable
    op.alter_column('students', 'email', nullable=False)
    op.alter_column('students', 'password_hash', nullable=False)

    # Add unique constraint on email
    op.create_unique_constraint('uq_students_email', 'students', ['email'])


def downgrade() -> None:
    """Remove auth fields from students table."""
    op.drop_constraint('uq_students_email', 'students', type_='unique')
    op.drop_column('students', 'password_hash')
    op.drop_column('students', 'email')
