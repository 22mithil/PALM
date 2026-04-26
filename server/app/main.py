"""
PALM — FastAPI Application Entrypoint
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.api.v1 import router as api_v1_router
from app.api.v1.websockets.video_ws import router as video_ws_router
from app.api.v1.websockets.audio_ws import router as audio_ws_router
from app.api.v1.websockets.tutor_ws import router as tutor_ws_router
from app.db.session import async_engine, async_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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

    yield

    logger.info("Shutting down PALM server …")
    await async_engine.dispose()
    logger.info("Database connection pool disposed.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Personalized Adaptive Learning Mentor — AI tutoring API",
        version="0.2.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_v1_router, prefix=settings.API_V1_STR)
    app.include_router(video_ws_router, tags=["Video WebSocket"])
    app.include_router(audio_ws_router, tags=["Audio WebSocket"])
    app.include_router(tutor_ws_router, tags=["Tutor WebSocket"])

    @app.get("/health", tags=["Health"])
    async def health_check():
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "connected"}
        except Exception as exc:
            logger.error("Health check DB failure: %s", exc)
            return {"status": "degraded", "database": "disconnected"}

    return app


app = create_app()
