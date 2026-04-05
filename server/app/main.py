"""
PALM — FastAPI Application Entrypoint

Creates the FastAPI app with:
- CORS middleware
- API v1 router
- Health check endpoint
- Startup/shutdown lifecycle events for DB connection
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.api.v1 import router as api_v1_router
from app.db.session import async_engine, async_session_factory

logger = logging.getLogger(__name__)


# ── Lifecycle ────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle.

    - On startup: verify DB connectivity.
    - On shutdown: dispose the engine connection pool.
    """
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("Starting PALM server …")
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.close()
        logger.info("✅  Database connection verified.")
    except Exception as exc:
        logger.error("❌  Database connection failed: %s", exc)
        raise RuntimeError(
            "Could not connect to the database. Check DATABASE_URL."
        ) from exc

    yield  # ← app is running

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down PALM server …")
    await async_engine.dispose()
    logger.info("Database connection pool disposed.")


# ── App Factory ──────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Personalized Adaptive Learning Mentor — AI tutoring API",
        version="0.1.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──────────────────────────────────────────────────────
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    # ── Health Check ─────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Basic liveness probe. Returns DB connectivity status."""
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "connected"}
        except Exception as exc:
            logger.error("Health check DB failure: %s", exc)
            return {"status": "degraded", "database": "disconnected"}

    return app


app = create_app()
