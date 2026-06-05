"""Tests for apply_orchestration service.

Uses FakeFormSource + FakeEmbeddingAdapter + InMemoryVectorStore + MockAdapter
to avoid any network or real browser dependencies.
"""

from __future__ import annotations

import uuid

from app.apply.browser import FakeFormSource
from app.apply.strategies import GenericFormStrategy, GreenhouseFormStrategy
from app.apply.types import FormField
from app.db.models.application import Application
from app.db.models.job_posting import JobPosting
from app.db.models.profile_field import ProfileField
from app.db.models.user import User
from app.embeddings.fake import FakeEmbeddingAdapter
from app.llm.adapters.mock import MockAdapter
from app.llm.client import LLMClient
from app.services.apply_orchestration import enqueue_applications, process_application, run_queue
from app.services.autopilot import AutopilotConfig
from app.vectorstore.memory import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_BASIC_FIELDS = [
    FormField(name="full_name", label="Full Name", field_type="text", required=True),
    FormField(name="email", label="Email", field_type="email", required=True),
]

_KNOCKOUT_FIELDS = [
    FormField(
        name="work_authorization",
        label="Work Authorization",
        field_type="select",
        required=True,
        is_knockout=True,
        options=["Yes", "No"],
    ),
]


def _make_job(source: str = "linkedin_easy_apply") -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        source=source,
        source_url="https://example.com/job/1",
        source_id=str(uuid.uuid4()),
        company="Acme",
        title="Backend Engineer",
        raw_content="Python backend engineer.",
    )


async def _seed_user_and_job(session, *, source: str = "linkedin_easy_apply"):
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", name="Test User")
    session.add(user)
    job = _make_job(source=source)
    session.add(job)
    await session.flush()
    return user, job


async def _seed_profile(session, user_id: uuid.UUID, *, with_work_auth: bool = True):
    fields = [
        ProfileField(
            id=uuid.uuid4(),
            user_id=user_id,
            key="full_name",
            value="Jane Doe",
            is_knockout=False,
        ),
        ProfileField(
            id=uuid.uuid4(),
            user_id=user_id,
            key="email",
            value="jane@example.com",
            is_knockout=False,
        ),
    ]
    if with_work_auth:
        fields.append(
            ProfileField(
                id=uuid.uuid4(),
                user_id=user_id,
                key="work_authorization",
                value="Yes",
                is_knockout=True,
            )
        )
    for f in fields:
        session.add(f)
    await session.flush()


def _make_autopilot(
    *,
    mode: str = "full",
    daily_cap: int = 80,
    min_confidence: float = 0.5,
    min_fit: float = 0.3,
) -> AutopilotConfig:
    return AutopilotConfig(
        mode=mode,  # type: ignore[arg-type]
        auto_submit_sources=["linkedin_easy_apply", "mycareersfuture"],
        min_confidence=min_confidence,
        min_fit=min_fit,
        daily_cap=daily_cap,
    )


def _make_strategies(form_source: FakeFormSource):
    return [
        GreenhouseFormStrategy(form_source),
        GenericFormStrategy(form_source),
    ]


# ---------------------------------------------------------------------------
# enqueue_applications
# ---------------------------------------------------------------------------


class TestEnqueueApplications:
    async def test_creates_queued_applications(self, session) -> None:
        user, job = await _seed_user_and_job(session)

        apps = await enqueue_applications(session, user.id, [job.id])

        assert len(apps) == 1
        assert apps[0].status == "queued"
        assert apps[0].job_id == job.id
        assert apps[0].user_id == user.id

    async def test_deduplicates_existing_application(self, session) -> None:
        user, job = await _seed_user_and_job(session)

        apps1 = await enqueue_applications(session, user.id, [job.id])
        apps2 = await enqueue_applications(session, user.id, [job.id])

        assert apps1[0].id == apps2[0].id

    async def test_enqueue_multiple_jobs(self, session) -> None:
        user, job1 = await _seed_user_and_job(session)
        job2 = _make_job()
        session.add(job2)
        await session.flush()

        apps = await enqueue_applications(session, user.id, [job1.id, job2.id])

        assert len(apps) == 2
        job_ids = {a.job_id for a in apps}
        assert job1.id in job_ids
        assert job2.id in job_ids


# ---------------------------------------------------------------------------
# process_application — all-clear auto-submit
# ---------------------------------------------------------------------------


class TestProcessApplicationAutoSubmit:
    async def test_auto_submit_source_dry_run_false_produces_submitted(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS, captcha=False)
        adapter = MockAdapter(fn=lambda _: "test")
        llm = LLMClient(session=session, adapter=adapter)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            llm,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        assert attempt.outcome == "submitted"
        await session.refresh(app)
        assert app.status == "submitted"

    async def test_dry_run_true_sets_auto_filling_not_submitted(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=True,
        )

        # dry_run=True → form not submitted, outcome is 'queued', app is 'auto_filling'
        assert attempt.outcome == "queued"
        await session.refresh(app)
        assert app.status == "auto_filling"


# ---------------------------------------------------------------------------
# process_application — missing knockout → needs_review
# ---------------------------------------------------------------------------


class TestProcessApplicationMissingKnockout:
    async def test_missing_knockout_forces_review(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        # No work_authorization in profile
        await _seed_profile(session, user.id, with_work_auth=False)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_KNOCKOUT_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        # Missing knockout → gate returns review → no submit
        assert attempt.outcome == "queued"
        await session.refresh(app)
        assert app.status == "needs_review"
        assert len(form_source.submitted_field_maps) == 0


# ---------------------------------------------------------------------------
# process_application — captcha → blocked
# ---------------------------------------------------------------------------


class TestProcessApplicationCaptcha:
    async def test_captcha_blocks_application(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        # FakeFormSource with captcha=True simulates CAPTCHA on submit
        form_source = FakeFormSource(_BASIC_FIELDS, captcha=True)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        assert attempt.outcome == "blocked"
        await session.refresh(app)
        assert app.status == "blocked"
        assert attempt.blocked_reason is not None


# ---------------------------------------------------------------------------
# process_application — daily cap exceeded → forced review
# ---------------------------------------------------------------------------


class TestProcessApplicationDailyCap:
    async def test_daily_cap_exceeded_forces_review(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        # daily_cap=0 means any existing submission exceeds cap; but here we
        # set cap=0 so count(0) >= cap(0) → exceeded.
        autopilot = _make_autopilot(mode="full", daily_cap=0)

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        assert attempt.outcome == "queued"
        await session.refresh(app)
        assert app.status == "needs_review"
        assert len(form_source.submitted_field_maps) == 0


# ---------------------------------------------------------------------------
# run_queue — batch isolation
# ---------------------------------------------------------------------------


class TestRunQueue:
    async def test_run_queue_returns_correct_counts_with_review(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        # No profile → knockout missing → needs_review
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_KNOCKOUT_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        counts = await run_queue(
            session,
            None,
            embed,
            store,
            user.id,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            dry_run=False,
        )

        assert counts["needs_review"] == 1
        assert counts["submitted"] == 0
        assert counts["failed"] == 0

    async def test_run_queue_isolates_failing_app(self, session) -> None:
        """An app whose job is missing causes a failure without crashing others."""
        user, good_job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)

        # Good app
        good_app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=good_job.id, status="queued"
        )
        # Bad app — nonexistent job_id
        bad_app = Application(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=uuid.uuid4(),  # no such job
            status="queued",
        )
        session.add(good_app)
        session.add(bad_app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        counts = await run_queue(
            session,
            None,
            embed,
            store,
            user.id,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            dry_run=True,
        )

        # bad_app is counted as failed; good_app processed dry_run=True → auto_filling
        # (auto_filling is the expected outcome for a dry_run auto_submit; it does not
        # map to any of the 4 counted buckets — only submitted/needs_review/blocked/failed)
        assert counts["failed"] == 1
        # good_app's dry_run outcome ('queued' + app.status='auto_filling') is not
        # counted in any bucket; only the error path increments failed.
        assert counts["submitted"] == 0

    async def test_run_queue_submitted_count(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()

        counts = await run_queue(
            session,
            None,
            embed,
            store,
            user.id,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            dry_run=False,
        )

        assert counts["submitted"] == 1
        assert counts["needs_review"] == 0
        assert counts["failed"] == 0


# ---------------------------------------------------------------------------
# Fix 1 regression: knockout detection by KNOCKOUT_KEYS name (is_knockout=False)
# ---------------------------------------------------------------------------


class TestKnockoutByName:
    """Regression for fix #1: a field with is_knockout=False but name in KNOCKOUT_KEYS
    must still force needs_review when the profile value is absent, even when all
    other fields are high-confidence.
    """

    async def test_visa_status_no_flag_no_profile_forces_review(self, session) -> None:
        """visa_status with is_knockout=False and no profile value → needs_review."""
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        # Seed profile for the trivial fields but NOT for visa_status
        await _seed_profile(session, user.id, with_work_auth=False)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        # visa_status has is_knockout=False but its name is in KNOCKOUT_KEYS
        visa_field = FormField(
            name="visa_status",
            label="Visa Status",
            field_type="select",
            required=True,
            is_knockout=False,  # flag deliberately False to test name-based detection
            options=["Citizen", "PR", "EP", "WP", "None"],
        )
        fields = list(_BASIC_FIELDS) + [visa_field]

        form_source = FakeFormSource(fields)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        # Must be queued for review, NOT auto-submitted
        assert attempt.outcome == "queued"
        await session.refresh(app)
        assert app.status == "needs_review"
        assert len(form_source.submitted_field_maps) == 0, (
            "Application must NOT be submitted when a KNOCKOUT_KEY field is unresolved"
        )


# ---------------------------------------------------------------------------
# Fix 2 regression: captcha detected early (before gate), blocks submission
# ---------------------------------------------------------------------------


class TestCaptchaEarlyDetection:
    """Regression for fix #2: captcha=True with dry_run=True must block immediately;
    submit_form must never be called.
    """

    async def test_captcha_true_dry_run_true_outcome_blocked(self, session) -> None:
        user, job = await _seed_user_and_job(session, source="linkedin_easy_apply")
        await _seed_profile(session, user.id)
        app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job.id, status="queued"
        )
        session.add(app)
        await session.flush()

        # captcha=True simulates a bot-wall on the form page
        form_source = FakeFormSource(_BASIC_FIELDS, captcha=True, dry_run=True)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        autopilot = _make_autopilot(mode="full")

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=True,
        )

        assert attempt.outcome == "blocked"
        await session.refresh(app)
        assert app.status == "blocked"
        # submit_form must never have been called
        assert len(form_source.submitted_field_maps) == 0, (
            "submit_form must NOT be called when captcha is detected"
        )


# ---------------------------------------------------------------------------
# Fix 5 regression: daily cap is total across ALL sources
# ---------------------------------------------------------------------------


class TestDailyCapCrossSource:
    """Regression for fix #5: daily cap counts submitted apps across all sources,
    not just the current job's source.
    """

    async def test_cap_counts_across_different_sources(self, session) -> None:
        from datetime import UTC, datetime

        from app.db.models.job_posting import JobPosting as JP

        user, job1 = await _seed_user_and_job(session, source="linkedin_easy_apply")
        # Second job on a different source
        job2 = JP(
            id=uuid.uuid4(),
            source="mycareersfuture",
            source_url="https://mcf.gov.sg/job/2",
            source_id=str(uuid.uuid4()),
            company="Beta Corp",
            title="Backend Engineer",
            raw_content="",
        )
        session.add(job2)
        await session.flush()

        # Simulate an already-submitted application on job2 (different source)
        existing_app = Application(
            id=uuid.uuid4(),
            user_id=user.id,
            job_id=job2.id,
            status="submitted",
            submitted_at=datetime.now(UTC),
        )
        session.add(existing_app)
        await session.flush()

        await _seed_profile(session, user.id)
        new_app = Application(
            id=uuid.uuid4(), user_id=user.id, job_id=job1.id, status="queued"
        )
        session.add(new_app)
        await session.flush()

        form_source = FakeFormSource(_BASIC_FIELDS)
        embed = FakeEmbeddingAdapter(dim=64)
        store = InMemoryVectorStore()
        # cap=1: the existing submission on job2 should count and hit the cap
        autopilot = _make_autopilot(mode="full", daily_cap=1)

        attempt = await process_application(
            session,
            None,
            embed,
            store,
            user.id,
            new_app,
            strategies=_make_strategies(form_source),
            form_source=form_source,
            autopilot=autopilot,
            dry_run=False,
        )

        # Cross-source submission counts → cap hit → needs_review
        assert attempt.outcome == "queued"
        await session.refresh(new_app)
        assert new_app.status == "needs_review"
        assert len(form_source.submitted_field_maps) == 0


# ---------------------------------------------------------------------------
# Fix 6 regression: enqueue (user_id, job_id) uniqueness — double-enqueue yields one row
# ---------------------------------------------------------------------------


class TestEnqueueUniqueness:
    """Regression for fix #6: enqueueing the same (user_id, job_id) twice must
    return the same Application row (not create two rows).
    """

    async def test_double_enqueue_yields_one_row(self, session) -> None:
        user, job = await _seed_user_and_job(session)

        apps1 = await enqueue_applications(session, user.id, [job.id])
        apps2 = await enqueue_applications(session, user.id, [job.id])

        assert apps1[0].id == apps2[0].id, (
            "Enqueueing the same (user_id, job_id) twice must return one row"
        )
