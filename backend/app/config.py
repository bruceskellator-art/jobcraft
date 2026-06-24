from __future__ import annotations

import functools
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ so non-Settings env vars (e.g. DEEPSEEK_API_KEY,
# ANTHROPIC_API_KEY) are available to adapters that read them via os.environ.
load_dotenv(override=False)


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

    # Provider selection — lets you run with only a DeepSeek key (no Anthropic/OpenAI/Qdrant).
    # JOBCRAFT_LLM_PROVIDER=deepseek  → use DeepSeek (needs DEEPSEEK_API_KEY)
    # JOBCRAFT_LLM_PROVIDER=openai    → use OpenAI  (needs OPENAI_API_KEY)
    # JOBCRAFT_LLM_PROVIDER=anthropic → use Anthropic (default; needs ANTHROPIC_API_KEY)
    llm_provider: Literal["anthropic", "openai", "deepseek"] = Field(default="anthropic")

    # JOBCRAFT_EMBEDDING_PROVIDER=fake  → deterministic BoW hashing, no API key needed
    # JOBCRAFT_EMBEDDING_PROVIDER=openai → real OpenAI embeddings (default)
    embedding_provider: Literal["openai", "fake"] = Field(default="openai")

    # JOBCRAFT_VECTOR_STORE=memory → in-process store, no Qdrant needed
    # JOBCRAFT_VECTOR_STORE=qdrant → production Qdrant (default)
    vector_store: Literal["qdrant", "memory"] = Field(default="qdrant")

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
