"""
Database initialization utilities.

For development convenience only — production should use Alembic migrations.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables defined in Base.metadata.

    **Warning:** This is a dev-only convenience. Use Alembic migrations for
    production schema management.
    """
    # Import all models so they register with Base.metadata
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
