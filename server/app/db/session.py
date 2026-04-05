"""
Async SQLAlchemy engine and session factory for NeonDB (PostgreSQL).

Uses asyncpg as the async driver with connection pooling tuned for
serverless PostgreSQL (NeonDB).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Async Engine ─────────────────────────────────────────────────────────
async_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    # ── Connection Pool ──────────────────────────────────────────────
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,       # Verify connections before checkout
    pool_recycle=300,          # Recycle connections every 5 min (NeonDB idle timeout)
    # ── asyncpg connect args ─────────────────────────────────────────
    connect_args={
        "ssl": "require",     # NeonDB requires SSL
    },
)

# ── Session Factory ──────────────────────────────────────────────────────
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, ensuring cleanup on exit.

    Usage with FastAPI ``Depends``::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
