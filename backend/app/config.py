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


@functools.lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
