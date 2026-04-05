"""
Application configuration using Pydantic BaseSettings.

Reads from environment variables and .env file in the project root.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve the .env file path (project root, two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Central configuration — all values sourced from env vars / .env."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Project ──────────────────────────────────────────────────────────
    PROJECT_NAME: str = "PALM"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── FastRouter ───────────────────────────────────────────────────────
    FASTROUTER_API_KEY: str = ""
    FASTROUTER_BASE_URL: str = "https://go.fastrouter.ai/api/v1"
    FASTROUTER_CHAT_MODEL: str = "gpt-4o"
    FASTROUTER_EMBEDDING_MODEL: str = "text-embedding-3-small"
    FASTROUTER_MAX_RETRIES: int = 3
    FASTROUTER_TIMEOUT: int = 30

    # ── Pinecone ─────────────────────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "palm-fyp"
    PINECONE_ENVIRONMENT: str = "us-east-1"

    @property
    def async_database_url(self) -> str:
        """Convert a standard postgresql:// URL to postgresql+asyncpg://.

        Also strips query params that asyncpg does not support
        (sslmode, channel_binding) — SSL is configured via connect_args instead.
        """
        import re

        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Strip params not supported by asyncpg (SSL handled via connect_args)
        url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
        url = re.sub(r"[&?]sslmode=[^&]*", "", url)
        # Clean up possible dangling '?' with no params
        url = re.sub(r"\?$", "", url)
        return url


settings = Settings()  # type: ignore[call-arg]
