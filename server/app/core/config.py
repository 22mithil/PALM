"""
Application configuration using Pydantic BaseSettings.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
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

    # ── Auth / JWT ───────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    @property
    def async_database_url(self) -> str:
        import re
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
        url = re.sub(r"[&?]sslmode=[^&]*", "", url)
        url = re.sub(r"\?$", "", url)
        return url


settings = Settings()  # type: ignore[call-arg]
