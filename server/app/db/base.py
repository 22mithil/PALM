"""
SQLAlchemy declarative base.

All ORM models inherit from `Base` defined here.
Import this module (or import models via app.models) before running
Alembic autogenerate so that metadata is populated.
"""

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass
