"""Matcher service: two-stage job-match scoring.

Cost-vs-quality rationale
--------------------------
Stage 1 (embedding prefilter) is O(n) cosine arithmetic — microseconds per job,
no LLM cost. It computes a single float (corpus-centroid cosine) that is good
enough to skip obviously irrelevant jobs before committing LLM budget.

Stage 2 (LLM-as-judge) is expensive (~1-3K tokens per match) but produces
structured dimension scores, gap analysis, and a human-readable rationale that
drive the resume tailoring and UI display. It runs only for jobs that pass the
stage-1 threshold (default 0.0 = always run, useful during development).

In production: set stage1_threshold ~0.3 to skip the bottom tercile of semantic
matches and reduce LLM spend by roughly 30-50% with minimal quality loss.
"""

from __future__ import annotations

import logging
import math
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.experience_item import ExperienceItem
from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.db.models.prompt_version import PromptVersion
from app.embeddings.base import EmbeddingClient
from app.matcher.types import MatchResult
from app.repositories.match import MatchRepository
from app.services.embed_pipeline import _compose_jd_text, user_corpus_vectors
from app.vectorstore.base import VectorStore

logger = logging.getLogger(__name__)

_PROMPT_NAME = "score_match"
_PROMPT_VERSION = 1
_PROMPT_MODEL = "claude-sonnet-4-6"
_PROMPT_TEMPERATURE = 0.0
_PROMPT_TEMPLATE = """\
You are an expert technical recruiter and career coach scoring a candidate's fit
for a job posting.

Score the candidate on each of these dimensions (0.0 = no match, 1.0 = perfect):
- skills: technical and domain skills alignment
- seniority: years of experience and scope of impact alignment
- domain: industry / business domain alignment
- culture: culture-signal and working-style alignment

Identify the top 3 skill gaps (skills the job requires that the candidate lacks
or has weakly). For each gap provide severity (low/mid/high) and a one-sentence
rationale.

Also identify which experience item IDs best support this match
(matched_experiences list; use empty list if none are particularly relevant).

Return ONLY a JSON object matching exactly this schema — no prose, no fences:
{
  "overall_score": <float 0..1, weighted average of dimensions>,
  "dimension_scores": {
    "skills": <float>, "seniority": <float>, "domain": <float>, "culture": <float>
  },
  "gaps": [{"skill": "<name>", "severity": "<low|mid|high>", "rationale": "<sentence>"}],
  "rationale": "<2-3 sentence overall rationale>",
  "matched_experiences": ["<uuid>", ...]
}

<job_description>
{{ job_description }}
</job_description>

<experience_items>
{{ experience_items }}
</experience_items>
"""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    total = [0.0] * dim
    for vec in vectors:
        for i, v in enumerate(vec):
            total[i] += v
    n = len(vectors)
    return [t / n for t in total]


async def ensure_match_prompt(session: AsyncSession) -> PromptVersion:
    """Return the active score_match PromptVersion, creating it if absent.

    Idempotent: safe under concurrent callers via IntegrityError retry.
    """
    result = await session.execute(
        select(PromptVersion).where(
            PromptVersion.name == _PROMPT_NAME,
            PromptVersion.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    prompt = PromptVersion(
        name=_PROMPT_NAME,
        version=_PROMPT_VERSION,
        template=_PROMPT_TEMPLATE,
        model=_PROMPT_MODEL,
        temperature=_PROMPT_TEMPERATURE,
        is_active=True,
    )
    session.add(prompt)
    try:
        await session.flush()
        await session.refresh(prompt)
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(PromptVersion).where(
                PromptVersion.name == _PROMPT_NAME,
                PromptVersion.is_active == True,  # noqa: E712
            )
        )
        prompt = result.scalar_one()
    return prompt


async def prefilter_score(
    session: AsyncSession,
    embed: EmbeddingClient,
    user_id: uuid.UUID,
    job: JobPosting,
) -> float:
    """Stage 1: cosine similarity between JD embedding and user corpus centroid.

    Returns a float in [-1, 1]. Returns 0.0 if the user has no experience items.
    """
    corpus = await user_corpus_vectors(session, embed, user_id)
    if not corpus:
        logger.debug("prefilter_score: user %s has no experience items", user_id)
        return 0.0

    jd_text = _compose_jd_text(job)
    jd_vectors = await embed.embed([jd_text])
    jd_vec = jd_vectors[0]

    centroid = _centroid(corpus)
    score = _cosine(jd_vec, centroid)
    logger.debug("prefilter_score: user=%s job=%s score=%.3f", user_id, job.id, score)
    return score


async def judge_match(
    session: AsyncSession,
    llm: object,
    job: JobPosting,
    experience_items: list[ExperienceItem],
) -> MatchResult:
    """Stage 2: LLM-as-judge structured scoring.

    Sends the JD and experience items to the LLM and returns a parsed MatchResult.
    """
    from app.llm.client import LLMClient

    assert isinstance(llm, LLMClient)

    prompt = await ensure_match_prompt(session)

    jd_text = _compose_jd_text(job)

    items_text = "\n\n".join(
        f"{i + 1}. [{item.kind}] {item.title or '(untitled)'} (id={item.id})\n{item.content}"
        for i, item in enumerate(experience_items)
    )

    response = await llm.complete(
        prompt.id,
        inputs={
            "job_description": jd_text,
            "experience_items": items_text,
        },
        response_model=MatchResult,
    )
    return response.parsed  # type: ignore[return-value]


async def compute_match(
    session: AsyncSession,
    llm: object,
    embed: EmbeddingClient,
    store: VectorStore,
    user_id: uuid.UUID,
    job: JobPosting,
    *,
    stage1_threshold: float = 0.0,
) -> Match:
    """Run both matching stages and persist the result.

    Stage 1 (cheap): cosine prefilter. If stage1 < stage1_threshold the LLM
    stage is skipped and a score-only Match is recorded immediately.

    Stage 2 (expensive): LLM-as-judge deep scoring. Always runs when
    stage1_threshold=0.0 (the safe default for development / demos).

    The resulting Match respects the UNIQUE(user_id, job_id, prompt_version_id)
    constraint via MatchRepository.upsert — a second call updates the row rather
    than inserting a duplicate.
    """
    stage1 = await prefilter_score(session, embed, user_id, job)

    # Load experience items for the LLM call
    result = await session.execute(
        select(ExperienceItem).where(ExperienceItem.user_id == user_id)
    )
    experience_items = list(result.scalars().all())

    prompt = await ensure_match_prompt(session)

    if stage1 < stage1_threshold:
        logger.info(
            "compute_match: stage1=%.3f below threshold=%.3f, skipping LLM for job %s",
            stage1,
            stage1_threshold,
            job.id,
        )
        repo = MatchRepository(session)
        return await repo.upsert(
            user_id=user_id,
            job_id=job.id,
            prompt_version_id=prompt.id,
            overall_score=stage1,
            dimension_scores={},
            gaps=[],
            rationale="Skipped LLM stage: below prefilter threshold.",
        )

    match_result = await judge_match(session, llm, job, experience_items)

    repo = MatchRepository(session)
    return await repo.upsert(
        user_id=user_id,
        job_id=job.id,
        prompt_version_id=prompt.id,
        overall_score=match_result.overall_score,
        dimension_scores=match_result.dimension_scores,
        gaps=[g.model_dump() for g in match_result.gaps],
        rationale=match_result.rationale,
    )
