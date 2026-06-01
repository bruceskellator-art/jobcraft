"""JobCraft CLI entry point.

Usage:
    jobcraft eval run <suite_name> [--prompt-version <name>] [--mock]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_SUITES_DIR = _REPO_ROOT / "eval" / "suites"


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------


def _print_table(rows: list[tuple[str, str, str, str]], header: tuple[str, str, str, str]) -> None:
    col_widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(4)]
    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*header))
    print("  ".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt.format(*row))


def _format_score(score: float | None) -> str:
    if score is None:
        return "-"
    return f"{score:.3f}"


def _print_suite_results(eval_run: object, suite_result_data: list[dict]) -> None:  # type: ignore[type-arg]
    """Print per-case and per-assertion results plus aggregate."""
    rows: list[tuple[str, str, str, str]] = []
    for case_data in suite_result_data:
        case_id = case_data["case_id"]
        case_passed = "PASS" if case_data["passed"] else "FAIL"
        case_score = _format_score(case_data.get("score"))
        rows.append((case_id, case_passed, case_score, ""))
        for ar in case_data.get("assertions", []):
            kind = ar["kind"]
            ar_passed = "  PASS" if ar["passed"] else "  FAIL"
            ar_score = _format_score(ar.get("score"))
            detail = ar.get("detail", "")[:60]
            rows.append((f"  {kind}", ar_passed, ar_score, detail))

    _print_table(rows, ("case / assertion", "result", "score", "detail"))

    print()
    from app.db.models.eval_run import EvalRun as _EvalRun  # noqa: F401
    agg = getattr(eval_run, "aggregate_scores", {})
    print("Aggregate:")
    for key, val in agg.items():
        print(f"  {key}: {val:.3f}")


# ---------------------------------------------------------------------------
# Dependency builders
# ---------------------------------------------------------------------------


def build_mock_deps() -> tuple:  # type: ignore[type-arg]
    """Build a (llm_factory, embed, store) triple of offline mock deps.

    The llm_factory binds a fresh LLMClient (sharing one MockAdapter) to each
    per-case session the runner creates, so no session is shared across cases.
    """
    import json

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.embeddings.fake import FakeEmbeddingAdapter
    from app.llm.adapters.mock import MockAdapter
    from app.llm.client import LLMClient
    from app.vectorstore.memory import InMemoryVectorStore

    _RESUME_MD = (
        "# Eval Candidate\n\n"
        "- Built AI systems using Python and machine learning techniques.\n"
        "- Led cross-functional team delivering product improvements.\n"
        "- Deployed scalable infrastructure handling 1M requests/day.\n"
        "- Applied Python, SQL, and data engineering skills across projects.\n"
    )

    _groundedness_payload = json.dumps({
        "claims": [
            {"text": "Built AI systems", "experience_id": None, "grounded": True},
        ],
        "grounded_ratio": 1.0,
        "ungrounded": [],
    })

    _judge_payload = json.dumps({"score": 0.85, "rationale": "Good quality resume"})

    def _fn(prompt: str) -> str:
        p = prompt.lower()
        if "expert evaluator" in p:
            return _judge_payload
        if "anti-hallucination" in p:
            return _groundedness_payload
        # Default: resume generation
        return json.dumps({"markdown": _RESUME_MD})

    adapter = MockAdapter(fn=_fn)

    def _llm_factory(session: AsyncSession) -> LLMClient:
        return LLMClient(session=session, adapter=adapter)

    embed = FakeEmbeddingAdapter(dim=64)
    store = InMemoryVectorStore()
    return _llm_factory, embed, store


async def _resolve_prompt_version(
    session: object,
    prompt_version_name: str | None,
) -> uuid.UUID:
    """Return the UUID for the named (active) prompt version, or the resume default."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.prompt_version import PromptVersion
    from app.generator.service import ensure_resume_prompt

    typed: AsyncSession = session  # type: ignore[assignment]

    if prompt_version_name is not None:
        result = await typed.execute(
            select(PromptVersion).where(
                PromptVersion.name == prompt_version_name,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        pv = result.scalar_one_or_none()
        if pv is None:
            raise ValueError(f"No active prompt version named '{prompt_version_name}'")
        return pv.id

    # Default: ensure the standard resume prompt exists and return its id
    pv = await ensure_resume_prompt(typed)
    return pv.id


# ---------------------------------------------------------------------------
# eval run subcommand
# ---------------------------------------------------------------------------


async def _cmd_eval_run(
    suite_name: str,
    prompt_version_name: str | None,
    mock: bool,
) -> int:
    """Run a named eval suite. Returns exit code (0=pass, 1=fail, 2=error)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.db.models  # noqa: F401 — registers all models
    from app.db.base import Base, make_session_factory
    from app.eval.loader import load_suite
    from app.eval.runner import run_suite

    suite_path = _EVAL_SUITES_DIR / f"{suite_name}.yaml"
    if not suite_path.exists():
        print(f"ERROR: Suite file not found: {suite_path}", file=sys.stderr)
        return 2

    suite = load_suite(suite_path)
    print(f"Suite: {suite.name}  ({len(suite.cases)} case(s))")
    print(f"Description: {suite.description}")
    print()

    if mock:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        import os
        db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        engine = create_async_engine(db_url, echo=False)

    session_factory = make_session_factory(engine)

    try:
        # Build deps: an LLM factory (per-case-session-safe) plus embed/store.
        if mock:
            llm_factory, embed, store = build_mock_deps()
        else:
            import os

            from sqlalchemy.ext.asyncio import AsyncSession

            from app.embeddings.openai_adapter import OpenAIEmbeddingAdapter
            from app.llm.adapters.anthropic import AnthropicAdapter
            from app.llm.client import LLMClient
            from app.vectorstore.qdrant_adapter import QdrantVectorStore

            _anthropic_adapter = AnthropicAdapter()

            def llm_factory(session: AsyncSession) -> LLMClient:
                return LLMClient(session=session, adapter=_anthropic_adapter)

            embed = OpenAIEmbeddingAdapter()
            store = QdrantVectorStore(url=os.environ["QDRANT_URL"])

        try:
            # Resolve (and commit) the prompt version on its own session so the
            # EvalRun FK is satisfiable before run_suite persists it.
            async with session_factory() as setup_session:
                prompt_version_id = await _resolve_prompt_version(
                    setup_session, prompt_version_name
                )
                await setup_session.commit()

            eval_run = await run_suite(
                session_factory,
                suite,
                prompt_version_id=prompt_version_id,
                llm_factory=llm_factory,
                embed=embed,
                store=store,
            )
        except Exception as exc:
            print(f"ERROR: Suite run failed: {exc}", file=sys.stderr)
            return 2

        print(f"Run ID: {eval_run.id}")
        print()
        _print_suite_results(eval_run, eval_run.results)

        pass_rate = eval_run.aggregate_scores.get("pass_rate", 0.0)
        print()
        if pass_rate >= 1.0:
            print(f"PASSED  pass_rate={pass_rate:.3f}")
            return 0
        else:
            print(f"FAILED  pass_rate={pass_rate:.3f}")
            return 1

    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobcraft", description="JobCraft CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    eval_parser = subparsers.add_parser("eval", help="Eval commands")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)

    run_parser = eval_sub.add_parser("run", help="Run an eval suite")
    run_parser.add_argument("suite_name", help="Name of the eval suite (without .yaml)")
    run_parser.add_argument(
        "--prompt-version",
        dest="prompt_version",
        default=None,
        help="Name of the active PromptVersion to use",
    )
    run_parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use mock LLM/embeddings for offline testing",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "eval" and args.eval_command == "run":
        exit_code = asyncio.run(
            _cmd_eval_run(
                args.suite_name,
                args.prompt_version,
                args.mock,
            )
        )
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
