from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apply.browser import FormSource, PlaywrightFormSource
from app.apply.strategies import ApplyStrategy, GenericFormStrategy, GreenhouseFormStrategy
from app.config import get_settings
from app.db.base import _get_session_factory, get_session
from app.db.models.email_account import EmailAccount
from app.db.models.user import User
from app.email_sync.crypto import TokenCrypto
from app.email_sync.provider import EmailProvider, GmailProvider, OutlookProvider
from app.embeddings.base import EmbeddingClient
from app.embeddings.fake import FakeEmbeddingAdapter
from app.embeddings.openai_adapter import OpenAIEmbeddingAdapter
from app.generator.pdf import NullPdfRenderer, PdfRenderer
from app.llm.adapters.anthropic import AnthropicAdapter
from app.llm.adapters.base import LLMAdapter
from app.llm.adapters.deepseek import DeepSeekAdapter
from app.llm.adapters.openai import OpenAIAdapter
from app.llm.client import LLMClient
from app.scrapers.base import JobSource
from app.scrapers.greenhouse import GreenhouseSource
from app.scrapers.lever import LeverSource
from app.vectorstore.base import VectorStore
from app.vectorstore.memory import InMemoryVectorStore
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


def _build_llm_adapter() -> LLMAdapter:
    """Return the LLM adapter selected by JOBCRAFT_LLM_PROVIDER."""
    provider = get_settings().llm_provider
    if provider == "deepseek":
        return DeepSeekAdapter()
    if provider == "openai":
        return OpenAIAdapter()
    return AnthropicAdapter()


def get_llm_client(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> LLMClient:
    """Build an LLMClient using the adapter selected by JOBCRAFT_LLM_PROVIDER.

    Defaults to AnthropicAdapter. Set JOBCRAFT_LLM_PROVIDER=deepseek to use
    DeepSeek, or JOBCRAFT_LLM_PROVIDER=openai to use OpenAI.

    In tests, override this dependency with a MockAdapter-backed LLMClient:

        app.dependency_overrides[get_llm_client] = lambda: LLMClient(session, MockAdapter(...))
    """
    return LLMClient(session=session, adapter=_build_llm_adapter())


def get_embedding_client() -> EmbeddingClient:
    """Build an embedding client selected by JOBCRAFT_EMBEDDING_PROVIDER.

    Defaults to OpenAIEmbeddingAdapter (requires OPENAI_API_KEY).
    Set JOBCRAFT_EMBEDDING_PROVIDER=fake to use the deterministic BoW fake
    adapter — no API key needed, suitable for local dev and demos.
    """
    if get_settings().embedding_provider == "fake":
        return FakeEmbeddingAdapter()
    return OpenAIEmbeddingAdapter()


def get_vector_store() -> VectorStore:
    """Build a vector store selected by JOBCRAFT_VECTOR_STORE.

    Defaults to QdrantVectorStore. Set JOBCRAFT_VECTOR_STORE=memory to use
    the in-process InMemoryVectorStore — no Qdrant required, suitable for
    local dev and demos.
    """
    if get_settings().vector_store == "memory":
        return InMemoryVectorStore()
    return QdrantVectorStore(url=get_settings().qdrant_url)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the application's async session factory.

    In tests, override with an in-memory factory bound to a test engine:

        app.dependency_overrides[get_session_factory] = lambda: make_session_factory(test_engine)
    """
    return _get_session_factory()


def get_llm_factory() -> Callable[[AsyncSession], LLMClient]:
    """Return a factory that builds an LLMClient (AnthropicAdapter) for a given session.

    The returned callable accepts an AsyncSession and produces a fresh LLMClient
    bound to that session.  run_suite calls this once per case, passing the
    case's own isolated session.

    In tests, override this dependency to inject a MockAdapter-backed factory:

        def _mock_llm_factory():
            adapter = MockAdapter(fn=my_fn)
            return lambda session: LLMClient(session=session, adapter=adapter)

        app.dependency_overrides[get_llm_factory] = _mock_llm_factory
    """
    _adapter = _build_llm_adapter()

    def _factory(session: AsyncSession) -> LLMClient:
        return LLMClient(session=session, adapter=_adapter)

    return _factory


def get_pdf_renderer() -> PdfRenderer:
    """Return a NullPdfRenderer by default.

    Swap to TypstRenderer when the ``typst`` binary is available:

        app.dependency_overrides[get_pdf_renderer] = lambda: TypstRenderer()

    Tests always use NullPdfRenderer to avoid the typst binary dependency.
    """
    return NullPdfRenderer()


def get_form_source() -> FormSource:
    """Return the default FormSource (PlaywrightFormSource stub).

    In tests, override with FakeFormSource to avoid network I/O:

        app.dependency_overrides[get_form_source] = lambda: FakeFormSource(fields=[...])
    """
    return PlaywrightFormSource()


def get_apply_strategies(
    form_source: FormSource = Depends(get_form_source),  # noqa: B008
) -> list[ApplyStrategy]:
    """Return the ordered list of ApplyStrategy instances.

    Greenhouse-specific strategy is tried first; GenericFormStrategy is the
    catch-all fallback.  In tests, override get_form_source instead.
    """
    return [
        GreenhouseFormStrategy(form_source),
        GenericFormStrategy(form_source),
    ]


def get_token_crypto() -> TokenCrypto:
    """Return a TokenCrypto instance backed by the configured Fernet key.

    Raises HTTP 503 if JOBCRAFT_TOKEN_ENCRYPTION_KEY is not set, which disables
    the email sync feature entirely in that deployment.

    In tests, override this dependency with a TokenCrypto built from a generated key:

        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        app.dependency_overrides[get_token_crypto] = lambda: TokenCrypto(key)
    """
    key = get_settings().token_encryption_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Email sync not configured — JOBCRAFT_TOKEN_ENCRYPTION_KEY is unset.",
        )
    return TokenCrypto(key)


def get_email_provider(account: EmailAccount) -> EmailProvider:
    """Build a provider instance for the given EmailAccount.

    Decrypts the account's stored token and constructs the appropriate provider.
    The token is used only to build the provider and is never logged or returned.

    In tests, override this factory or the get_token_crypto dependency and supply
    a FakeEmailProvider via the route's provider argument.
    """
    crypto = get_token_crypto()
    token = crypto.decrypt(account.oauth_token_enc)
    access_token: str = token.get("access_token", "")

    if account.provider == "gmail":
        return GmailProvider(access_token=access_token)
    if account.provider == "outlook":
        return OutlookProvider(access_token=access_token)

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported email provider: {account.provider!r}",
    )


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
