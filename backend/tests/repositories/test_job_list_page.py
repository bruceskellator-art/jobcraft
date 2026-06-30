"""Tests for JobRepository.list_page: filters, scored, fit sort, pagination."""

from __future__ import annotations

import uuid

from app.db.models.job_posting import JobPosting
from app.db.models.match import Match
from app.db.models.prompt_version import PromptVersion
from app.db.models.user import User
from app.repositories.job import JobRepository


async def _seed_user(session) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test")
    session.add(user)
    await session.flush()
    return user


async def _seed_prompt(session) -> PromptVersion:
    pv = PromptVersion(
        id=uuid.uuid4(),
        name="match",
        version=1,
        template="t",
        model="m",
        temperature=0.0,
    )
    session.add(pv)
    await session.flush()
    return pv


def _make_job(source: str, company: str, title: str) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source=source,
        source_url="https://example.com/j",
        source_id=str(uuid.uuid4()),
        company=company,
        title=title,
        raw_content="content",
    )


async def test_list_page_paginates(session) -> None:
    user = await _seed_user(session)
    for i in range(5):
        session.add(_make_job(f"greenhouse:c{i}", f"Co{i}", f"Engineer {i}"))
    await session.flush()
    repo = JobRepository(session)

    rows, total = await repo.list_page(user.id, limit=2, offset=0)
    assert total == 5
    assert len(rows) == 2

    rows2, total2 = await repo.list_page(user.id, limit=2, offset=4)
    assert total2 == 5
    assert len(rows2) == 1


async def test_list_page_source_category_match(session) -> None:
    user = await _seed_user(session)
    session.add(_make_job("greenhouse:acme", "Acme", "GH Role"))
    session.add(_make_job("lever:beta", "Beta", "Lever Role"))
    session.add(_make_job("linkedin", "Gamma", "LI Role"))
    await session.flush()
    repo = JobRepository(session)

    gh_rows, gh_total = await repo.list_page(user.id, source="greenhouse")
    assert gh_total == 1
    assert gh_rows[0][0].source == "greenhouse:acme"

    li_rows, li_total = await repo.list_page(user.id, source="linkedin")
    assert li_total == 1
    assert li_rows[0][0].source == "linkedin"


async def test_list_page_scored_filter_and_fit_sort(session) -> None:
    user = await _seed_user(session)
    pv = await _seed_prompt(session)
    scored_job = _make_job("greenhouse:acme", "Acme", "Scored")
    unscored_job = _make_job("greenhouse:beta", "Beta", "Unscored")
    session.add(scored_job)
    session.add(unscored_job)
    await session.flush()
    session.add(
        Match(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=scored_job.id,
            overall_score=0.75,
            dimension_scores={},
            gaps=[],
            rationale="r",
            prompt_version_id=pv.id,
        )
    )
    await session.flush()
    repo = JobRepository(session)

    # scored=True → only the matched job
    scored_rows, scored_total = await repo.list_page(user.id, scored=True)
    assert scored_total == 1
    assert scored_rows[0][0].id == scored_job.id
    assert scored_rows[0][1] is not None
    assert abs(scored_rows[0][1].overall_score - 0.75) < 1e-6

    # scored=False → only the unmatched job
    unscored_rows, unscored_total = await repo.list_page(user.id, scored=False)
    assert unscored_total == 1
    assert unscored_rows[0][0].id == unscored_job.id

    # min_fit excludes scores below threshold
    _, high_total = await repo.list_page(user.id, min_fit=0.8)
    assert high_total == 0

    # fit sort places the scored job first (nulls last)
    fit_rows, _ = await repo.list_page(user.id, sort="fit")
    assert fit_rows[0][0].id == scored_job.id
