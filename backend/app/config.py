from __future__ import annotations

import functools

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JOBCRAFT_",
        extra="ignore",
    )

    app_name: str = "JobCraft"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://jobcraft:jobcraft@localhost:5432/jobcraft",
    )
    qdrant_url: str = Field(default="http://localhost:6333")
    redis_url: str = Field(default="redis://localhost:6379/0")
    cors_origins: list[str] = Field(default=["http://localhost:3000"])

    # Email sync — set to a Fernet key generated via:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # None (default) disables email sync entirely.
    token_encryption_key: str | None = Field(
        default=None,
        description=(
            "Fernet symmetric key for encrypting OAuth tokens at rest. "
            "Must be a URL-safe base64-encoded 32-byte key. "
            "Set via JOBCRAFT_TOKEN_ENCRYPTION_KEY env var. "
            "None disables email sync."
        ),
    )


@functools.lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
