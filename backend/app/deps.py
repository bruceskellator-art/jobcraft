from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import get_session
from app.db.models.user import User
from app.embeddings.base import EmbeddingClient
from app.embeddings.openai_adapter import OpenAIEmbeddingAdapter
from app.generator.pdf import NullPdfRenderer, PdfRenderer
from app.llm.adapters.anthropic import AnthropicAdapter
from app.llm.client import LLMClient
from app.scrapers.base import JobSource
from app.scrapers.greenhouse import GreenhouseSource
from app.scrapers.lever import LeverSource
from app.vectorstore.base import VectorStore
from app.vectorstore.qdrant_adapter import QdrantVectorStore

# Phase-1 stand-in for real authentication.
# Returns (or creates) a single fixed developer user so that all routes
# have a current_user without a real auth system in place.
# Replace this dependency with a JWT/session resolver once auth is built.
_DEV_EMAIL = "dev@jobcraft.local"
_DEV_NAME = "Dev User"


async def get_current_user(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> User:
    """Return the dev user, creating it on first call.

    Phase-1 auth stub — not suitable for production.
    Raises HTTP 501 if called outside the development environment.
    """
    if get_settings().environment != "development":
        raise HTTPException(status_code=501, detail="Auth not configured")

    result = await session.execute(select(User).where(User.email == _DEV_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=_DEV_EMAIL, name=_DEV_NAME)
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
    return user


def get_llm_client(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> LLMClient:
    """Build an LLMClient backed by AnthropicAdapter for production use.

    In tests, override this dependency with a MockAdapter-backed LLMClient:

        app.dependency_overrides[get_llm_client] = lambda: LLMClient(session, MockAdapter(...))
    """
    return LLMClient(session=session, adapter=AnthropicAdapter())


def get_embedding_client() -> EmbeddingClient:
    """Build an OpenAIEmbeddingAdapter for production use.

    Reads OPENAI_API_KEY from the environment. In tests, override with
    FakeEmbeddingAdapter to avoid network calls:

        app.dependency_overrides[get_embedding_client] = lambda: FakeEmbeddingAdapter()
    """
    return OpenAIEmbeddingAdapter()


def get_vector_store() -> VectorStore:
    """Build a QdrantVectorStore pointed at the configured qdrant_url.

    In tests, override with InMemoryVectorStore to avoid a Qdrant connection:

        app.dependency_overrides[get_vector_store] = lambda: InMemoryVectorStore()
    """
    return QdrantVectorStore(url=get_settings().qdrant_url)


def get_pdf_renderer() -> PdfRenderer:
    """Return a NullPdfRenderer by default.

    Swap to TypstRenderer when the ``typst`` binary is available:

        app.dependency_overrides[get_pdf_renderer] = lambda: TypstRenderer()

    Tests always use NullPdfRenderer to avoid the typst binary dependency.
    """
    return NullPdfRenderer()


def get_source_factory() -> Callable[[list[str], list[str]], list[JobSource]]:
    """Return a factory that builds JobSource instances from board/company lists.

    The factory signature is:
        (greenhouse_boards: list[str], lever_companies: list[str]) -> list[JobSource]

    Each adapter created here owns its own httpx.AsyncClient.  The caller is
    responsible for calling ``aclose()`` on every source when done — or using
    each adapter as an async context manager.  The ``scrape_jobs`` route does
    this in a ``finally`` block.

    In tests, override this dependency to inject FakeSource instances
    without making any network calls:

        app.dependency_overrides[get_source_factory] = lambda: fake_factory
    """

    def _build(
        greenhouse_boards: list[str],
        lever_companies: list[str],
    ) -> list[JobSource]:
        sources: list[JobSource] = []
        for board in greenhouse_boards:
            sources.append(GreenhouseSource(board_token=board))  # type: ignore[arg-type]
        for company in lever_companies:
            sources.append(LeverSource(company=company))  # type: ignore[arg-type]
        return sources

    return _build
