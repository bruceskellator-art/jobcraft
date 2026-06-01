"""Admin API for eval suite management.

Routes
------
GET  /api/admin/evals          List recent EvalRun records (most recent first).
GET  /api/admin/evals/{run_id} Fetch a single EvalRun by ID.
POST /api/admin/evals/run      Trigger an eval suite run and return the result.

Security note
-------------
suite_name is validated with ``^[a-z0-9_]+$`` before being used to build a
filesystem path.  This prevents path traversal attacks (e.g. ``../etc/passwd``).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import get_session
from app.deps import (
    get_embedding_client,
    get_llm_factory,
    get_session_factory,
    get_vector_store,
)
from app.embeddings.base import EmbeddingClient
from app.llm.client import LLMClient
from app.repositories.eval_run import EvalRunRepository
from app.schemas.eval import EvalRunRead, RunSuiteRequest
from app.vectorstore.base import VectorStore

router = APIRouter(prefix="/api/admin/evals", tags=["admin", "evals"])

# Suites directory — resolved once at import time relative to the repo root.
# File is at backend/app/api/admin_evals.py; parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SUITES_DIR = _REPO_ROOT / "eval" / "suites"

# Only alphanumeric lowercase and underscore are permitted in suite names.
_SUITE_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _validate_suite_name(suite_name: str) -> None:
    """Raise HTTP 400 if suite_name contains unsafe characters."""
    if not _SUITE_NAME_RE.match(suite_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid suite_name. Only lowercase letters, digits, and underscores "
                "are allowed (regex: ^[a-z0-9_]+$)."
            ),
        )


def _resolve_suite_path(suite_name: str) -> Path:
    """Return the absolute path for a suite YAML, or raise HTTP 404 if absent.

    Resolves the path and confirms it stays inside _SUITES_DIR to guard
    against any remaining traversal edge cases (e.g. symlinks).
    """
    suite_path = (_SUITES_DIR / f"{suite_name}.yaml").resolve()
    if not str(suite_path).startswith(str(_SUITES_DIR.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolved suite path is outside the allowed suites directory.",
        )
    if not suite_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Suite '{suite_name}' not found.",
        )
    return suite_path


async def _resolve_prompt_version_id(
    session_factory: async_sessionmaker[AsyncSession],
    prompt_version_name: str | None,
) -> uuid.UUID:
    """Resolve (and commit) the prompt version, mirroring CLI wiring."""
    from sqlalchemy import select

    from app.db.models.prompt_version import PromptVersion
    from app.generator.service import ensure_resume_prompt

    async with session_factory() as session:
        if prompt_version_name is not None:
            result = await session.execute(
                select(PromptVersion).where(
                    PromptVersion.name == prompt_version_name,
                    PromptVersion.is_active == True,  # noqa: E712
                )
            )
            pv = result.scalar_one_or_none()
            if pv is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No active prompt version named '{prompt_version_name}'.",
                )
            prompt_version_id = pv.id
        else:
            pv = await ensure_resume_prompt(session)
            prompt_version_id = pv.id

        await session.commit()

    return prompt_version_id


@router.get("", response_model=list[EvalRunRead])
async def list_eval_runs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> list[EvalRunRead]:
    """Return recent EvalRun records, most recent first (limit 100)."""
    repo = EvalRunRepository(session)
    runs = await repo.list()
    return [EvalRunRead.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=EvalRunRead)
async def get_eval_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> EvalRunRead:
    """Return a single EvalRun by ID, or 404 if not found."""
    repo = EvalRunRepository(session)
    run = await repo.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EvalRun '{run_id}' not found.",
        )
    return EvalRunRead.model_validate(run)


@router.post("/run", response_model=EvalRunRead, status_code=status.HTTP_200_OK)
async def run_eval_suite(
    body: RunSuiteRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),  # noqa: B008
    llm_factory: Callable[[AsyncSession], LLMClient] = Depends(get_llm_factory),  # noqa: B008
    embed: EmbeddingClient = Depends(get_embedding_client),  # noqa: B008
    store: VectorStore = Depends(get_vector_store),  # noqa: B008
) -> EvalRunRead:
    """Trigger an eval suite run and return the persisted EvalRun.

    - Validates suite_name (^[a-z0-9_]+$) to prevent path traversal.
    - Resolves the suite YAML from eval/suites/<name>.yaml.
    - Resolves the prompt version (active default, or by name).
    - Calls run_suite with injected session_factory / llm_factory / embed / store.
    """
    from app.eval.loader import load_suite
    from app.eval.runner import run_suite

    _validate_suite_name(body.suite_name)
    suite_path = _resolve_suite_path(body.suite_name)

    try:
        suite = load_suite(suite_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    prompt_version_id = await _resolve_prompt_version_id(
        session_factory, body.prompt_version
    )

    eval_run = await run_suite(
        session_factory,
        suite,
        prompt_version_id=prompt_version_id,
        llm_factory=llm_factory,
        embed=embed,
        store=store,
    )

    return EvalRunRead.model_validate(eval_run)
