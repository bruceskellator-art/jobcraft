# JobCraft — Architecture

> Last updated: 2026-06-24. Phases 0–8 implemented (463 backend tests green; frontend builds clean).

---

## 1. Overview

JobCraft is a single-user AI job-targeting system that scrapes job listings (Singapore-focused), extracts structured signals from each posting, scores the user's fit using a two-stage embedding + LLM-as-judge matcher, and generates tailored resumes and cover letters where every claim is grounded in the user's recorded experience corpus. It then auto-applies at scale through a field-mapping agent that fills application forms, routes each attempt through a confidence gate, and either auto-submits where it is safe or surfaces the application for fast batch review — all while logging every LLM call for cost tracking, prompt versioning, and an offline eval harness that gates regressions in CI.

---

## 2. System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          User / Frontend                            │
│  /experience  /jobs  /jobs/[id]  /documents  /apply-queue           │
│  /settings    /admin/evals                                          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ REST (FastAPI)
┌───────────────────────────▼─────────────────────────────────────────┐
│                        app/api/ (routers)                           │
│  experience · jobs · match · generation · apply · answers · profile │
│  admin_evals · resume_import                                        │
└──┬──────────┬──────────┬──────────┬──────────┬──────────┬───────────┘
   │          │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼          ▼
Scrape    Extract    Match     Generate    Apply      Eval
   │          │          │          │          │          │
┌──▼──┐  ┌───▼───┐  ┌───▼───┐  ┌───▼───┐  ┌──▼──┐  ┌───▼───┐
│scra-│  │extrac-│  │match- │  │gener- │  │appl-│  │eval/  │
│pers/│  │tor/   │  │er/    │  │ator/  │  │y/   │  │runner │
└──┬──┘  └───┬───┘  └───┬───┘  └───┬───┘  └──┬──┘  └───┬───┘
   │          │          │          │          │          │
   └──────────┴──────────┴────┬─────┴──────────┘          │
                              │                            │
                    ┌─────────▼──────────┐                 │
                    │   app/llm/client   │◄────────────────┘
                    │  (single gateway)  │
                    └──────┬─────────────┘
                           │ logs every call
              ┌────────────▼────────────────────────────┐
              │  Postgres 16                            │
              │  llm_calls · prompt_versions · matches  │
              │  artifacts · applications · eval_runs   │
              └────────────┬────────────────────────────┘
                           │
              ┌────────────▼──────────┐
              │   Qdrant              │
              │  (experience vectors) │
              └───────────────────────┘

arq/Redis worker (apply_worker.py)
  └─ process_application_task  [async, per application_id]
```

**Cross-cutting concerns:** every LLM call passes through `LLMClient`, which records a `llm_calls` row (tokens, latency, cost, rendered prompt, response). The eval harness (`app/eval/`) consumes the same `LLMClient` so evals are also fully logged.

---

## 3. Component Map

| Module | Responsibility | Key types |
|---|---|---|
| `app/llm/` | Single access point for all LLM calls. Loads prompt template from `prompt_versions`, renders it, calls the adapter, measures latency, writes `LlmCall`, returns structured response. | `LLMClient`, `LLMAdapter` (Protocol), `AnthropicAdapter`, `OpenAIAdapter`, `MockAdapter`, `AdapterResult`, `LLMResponse[T]` |
| `app/scrapers/` | Fetches raw job listings from ATS boards (Greenhouse, Lever) and deduplicates by `(source, source_id)`. | `BaseScraper`, `GreenhouseScraper`, `LeverScraper`, `dedupe` |
| `app/extractor/` | Converts raw HTML/text job postings into structured `JobPosting.extracted` JSONB (required skills, seniority, culture signals). | `ExtractorService`, `ExtractedJob` |
| `app/embeddings/` | Protocol + adapters for text embedding. `OpenAIEmbeddingAdapter` for production; `FakeEmbeddingAdapter` for tests (no network). | `EmbeddingAdapter` (Protocol), `OpenAIEmbeddingAdapter`, `FakeEmbeddingAdapter` |
| `app/vectorstore/` | Protocol + adapters for ANN search over experience-item embeddings. | `VectorStore` (Protocol), `QdrantVectorStore`, `InMemoryVectorStore` |
| `app/matcher/` | Two-stage matching: (1) ANN retrieval via vectorstore to find candidate experience items, (2) LLM-as-judge to score dimensions and identify gaps. | `MatcherService`, `MatchResult`, `Gap` |
| `app/generator/` | Grounded resume + cover letter generation. All claims are verified against the experience corpus; a `GroundednessResult` model-validator recomputes `grounded_ratio` from individual `Claim` objects — it never trusts the LLM's self-reported values. | `GeneratorService`, `GeneratedDoc`, `ArtifactScores`, `GroundednessResult`, `Claim`, `StyleConfig` |
| `app/apply/` | Apply engine with field-mapper, gate, and strategies. Enforces hard safety invariants (see §6). | `FieldMapper`, `GateDecision`, `decide()`, `ApplyStrategy` (Protocol), `GreenhouseFormStrategy`, `GenericFormStrategy`, `select_strategy()` |
| `app/workers/` | arq background worker. Picks up queued applications, instantiates production adapters, runs the apply pipeline. | `process_application_task`, `WorkerSettings` |
| `app/eval/` | Offline eval runner. Loads YAML suites from `eval/`, runs assertions concurrently (one session per case), persists `EvalRun`. Used by the `jobcraft eval` CLI and `POST /api/admin/evals/run`. | `EvalRunner`, `run_suite()`, `EvalCase`, `EvalSuite`, `SuiteResult`, `LlmJudgeAssertion`, `GroundednessAssertion` |
| `app/services/` | Orchestration layer between routers and domain modules. | `MatchOrchestrationService`, `ApplyOrchestrationService`, `GenerationService`, `EmbedPipelineService`, `AutopilotService`, `NlFilterService`, `ResumeExtractService`, `ScrapeService` |
| `app/repositories/` | Thin async SQLAlchemy 2.0 repository layer; one class per aggregate root. | `JobRepository`, `MatchRepository`, `ArtifactRepository`, `ApplicationRepository`, `ExperienceRepository`, `ProfileFieldRepository`, `AnswerBankRepository`, `EvalRunRepository` |
| `app/db/models/` | SQLAlchemy ORM models. All use `PortableUUID` and `PortableArray` type variants so the test suite runs on SQLite with no containers. | See §4 |
| `app/api/` | FastAPI routers. All async, all use dependency injection via `app/deps.py`. | See §5 |
| `app/cli.py` | `jobcraft` Typer CLI. Exposes `eval` command; can be extended for scrape/match/generate batch runs. | `jobcraft eval [suite]` |
| `app/config.py` | `Settings` (pydantic-settings) loaded from env. Single `get_settings()` lru-cached factory. | `Settings` |

---

## 4. Data Model

All tables use UUID primary keys. `created_at` / `updated_at` default to `now()`.

| Table | Purpose | Key relationships |
|---|---|---|
| `users` | Identity (single user for now). `id`, `email`, `name`. | Root of all user-scoped data |
| `experience_items` | User's experience corpus: work, project, education, skill, achievement entries. Stores free-text `content` plus structured `tags` and `metadata` JSONB. Embedded into Qdrant for ANN retrieval. | `user_id → users` |
| `job_postings` | Scraped job listings. `raw_content` + structured `extracted` JSONB. Unique on `(source, source_id)`. | — |
| `matches` | Scored match between a user and a job for a specific prompt version. `overall_score`, `dimension_scores` JSONB, `gaps` JSONB, `rationale`. Unique on `(user_id, job_id, prompt_version_id)`. | `user_id → users`, `job_id → job_postings`, `prompt_version_id → prompt_versions` |
| `artifacts` | Generated resume or cover letter. `kind` (`resume`/`cover_letter`), `format` (`markdown`/`pdf`/`html`), full `content`, `scores` JSONB, `is_baseline` flag. | `user_id → users`, `job_id → job_postings` (nullable for baseline), `prompt_version_id → prompt_versions` |
| `applications` | One row per user–job pair. Tracks the full lifecycle status (`interested` → `queued` → `auto_filling` → `needs_review` → `submitted` / `blocked` / `failed` → `phone_screen` → `offer` / `rejected`). References the resume and cover letter artifact used. | `user_id → users`, `job_id → job_postings`, `resume_artifact_id → artifacts`, `cover_letter_artifact_id → artifacts` |
| `application_attempts` | One row per fill attempt (retries possible). Records `strategy`, `field_map` JSONB, `overall_confidence`, `outcome`, and optional `screenshot_path`. | `application_id → applications` |
| `profile_fields` | Key–value store for user profile data (name, email, phone, work authorization, etc.). `is_knockout` flag marks fields that must be sourced from profile only. Reserved key `__autopilot__` stores `AutopilotConfig` JSON. | `user_id → users` |
| `answer_bank` | Approved answers to common application questions. `approved` flag required before reuse; `reuse_count` tracked. | `user_id → users` |
| `prompt_versions` | Versioned prompt templates with model, temperature, and metadata. Partial unique index ensures at most one active version per name. | Referenced by `matches`, `artifacts`, `llm_calls`, `eval_runs` |
| `llm_calls` | Immutable audit log of every LLM call: rendered prompt, raw response, parsed response, token counts, latency, cost in USD, and any error. | `prompt_version_id → prompt_versions` |
| `eval_runs` | Persisted result of a full eval suite run: per-case results and aggregate scores. | `prompt_version_id → prompt_versions` |

> **Email status sync (Phase 8):** `email_accounts` (encrypted OAuth tokens, read-only scopes), `email_messages` (only mail matched to an application is persisted), `status_events` (proposed/applied/dismissed transitions) — power the automated inbox → status pipeline (§ Email Status Tracker).

---

## 5. API Surface

All routes are under the FastAPI app mounted at `http://localhost:8000`.

| Prefix / Group | Endpoints |
|---|---|
| **Health** | `GET /` · `GET /health` |
| **Experience** `GET POST /api/experience` | `GET /api/experience` — list · `POST /api/experience` — create · `GET /api/experience/{id}` · `PATCH /api/experience/{id}` · `DELETE /api/experience/{id}` · `POST /api/experience/import` (resume PDF import) |
| **Jobs** | `GET /api/jobs` (optional `?source=` `?q=`) · `GET /api/jobs/{id}` · `POST /api/jobs/scrape` |
| **Match** | `GET /api/jobs/{id}/match` · `POST /api/match/run` (batch, body `{limit: int}`) |
| **Generation** | `POST /api/jobs/{id}/generate` · `GET /api/jobs/{id}/artifacts` · `GET /api/artifacts` · `GET /api/artifacts/{id}` · `POST /api/artifacts/baseline` (PDF upload) |
| **Apply** | `POST /api/apply/queue` · `GET /api/apply/queue` (review queue) · `GET /api/applications` (optional `?status=`) · `POST /api/applications/{id}/process` · `POST /api/applications/{id}/approve` · `PATCH /api/applications/{id}/status` |
| **Answers** | `GET /api/answers` · `POST /api/answers` · `POST /api/answers/{id}/approve` · `GET /api/answers/suggest?question=` |
| **Profile** | `GET /api/profile/fields` · `PUT /api/profile/fields` · `DELETE /api/profile/fields/{key}` · `GET /api/profile/autopilot` · `PUT /api/profile/autopilot` |
| **Admin / Evals** | `GET /api/admin/evals` · `GET /api/admin/evals/{id}` · `POST /api/admin/evals/run` |

---

## 6. Key Design Decisions

### 6.1 Provider abstractions enable network-free tests

Three protocol/adapter pairs allow the full test suite (~370 tests) to run with no external services:

| Abstraction | Production | Test double |
|---|---|---|
| `LLMAdapter` | `AnthropicAdapter`, `OpenAIAdapter` | `MockAdapter` (returns canned `AdapterResult`) |
| `EmbeddingAdapter` | `OpenAIEmbeddingAdapter` | `FakeEmbeddingAdapter` (deterministic vectors) |
| `VectorStore` | `QdrantVectorStore` | `InMemoryVectorStore` |

SQLAlchemy models use `PortableUUID` and `PortableArray` helpers so Alembic migrations target Postgres while tests run on in-process SQLite.

### 6.2 LLMClient as single gateway

All LLM calls — matcher, generator, extractor, eval assertions — pass through `LLMClient.complete()`. The client:

1. Loads the named `PromptVersion` from Postgres
2. Renders the Jinja/string template with `inputs`
3. Calls the `LLMAdapter`
4. Writes a `LlmCall` row (tokens, latency, cost, rendered prompt, full response)
5. Optionally parses the response into a typed Pydantic model

This makes every AI call reproducible, auditable, and cost-tracked without any instrumentation at the call site.

### 6.3 Grounded generation with model-validated scores

`GroundednessResult` uses a Pydantic `model_validator` (post) to recompute `grounded_ratio` and the `ungrounded` list from the individual `Claim` objects returned by the LLM — it does **not** trust the LLM's self-reported aggregate. This prevents subtle hallucinations in the scoring layer from propagating forward.

### 6.4 Apply-engine hard safety invariants

The gate (`apply/gate.py`) is a pure function `decide(field_map, autopilot, match_score) -> GateDecision`. Hard invariants, checked in order:

1. **No CAPTCHA bypass** — if any form field signals a CAPTCHA challenge, outcome is `block`.
2. **Autopilot `mode="off"`** — immediately routes to `review`; the worker also returns `skipped` before any form interaction.
3. **Selective mode + source not in allowlist** — routes to `review`.
4. **Confidence below threshold** (`autopilot.min_confidence`, default 0.75) — routes to `review`.
5. **Match score below threshold** (`autopilot.min_fit`, default 0.55) — routes to `review`.
6. **Unresolved knockout fields** — any field with `is_knockout=True` that could not be sourced exclusively from `profile_fields` routes to `review`.
7. Only if all checks pass: `auto_submit`.

`KNOCKOUT_KEYS = {"work_authorization", "visa_status", "citizenship", "years_of_experience"}` — these fields may never be sourced from the answer bank, generated text, or any source other than `profile_fields`.

`AutopilotConfig.daily_cap` (default 80) is enforced by `ApplyOrchestrationService` before jobs are enqueued.

Dry-run is the default mode for `process_application_task` until `AutopilotConfig.mode` is explicitly set to `"selective"` or `"full"`.

### 6.5 Prompt versioning and eval CI gate

Every `PromptVersion` row has `(name, version)` as a unique key and a partial unique index ensuring at most one active version per name. Changing a prompt requires inserting a new version row; old outputs remain reproducible via their `prompt_version_id` foreign key.

The `jobcraft eval` CLI runs a named YAML suite (stored in `eval/`) against the live database and fails with a non-zero exit code if any assertion fails — used as a CI gate to prevent prompt regressions from shipping.

### 6.6 Savepoint isolation in batch runners

Both the eval runner (`eval/runner.py`) and the apply worker use per-case sessions (eval: `asyncio.gather` with one `session_factory()` call per case; apply: arq task receives a fresh context). Failures in one case do not roll back sibling cases.

---

## 7. Testing Strategy

| Layer | Approach |
|---|---|
| Unit | Pure functions (gate, scoring, type validators, adapters) tested in isolation |
| Integration | API routes tested with `AsyncClient` + SQLite in-memory DB; `MockAdapter` / `FakeEmbeddingAdapter` / `InMemoryVectorStore` injected via `app/deps.py` overrides |
| Eval / regression | YAML-driven eval suites in `eval/`; `LlmJudgeAssertion` uses `MockAdapter` in unit mode and real adapter in integration mode; `jobcraft eval` CLI used as CI gate |

**~370 tests** pass with no network, no running Postgres, and no running Qdrant. The test suite runs on SQLite via `PortableUUID` / `PortableArray` column type variants and async `AsyncSession` fixtures.

Framework: **pytest** + **pytest-asyncio** + **httpx** (`AsyncClient`).

---

## 8. Frontend Routes

| Route | Purpose |
|---|---|
| `/` | Dashboard — match scores, recent activity |
| `/experience` | Experience corpus CRUD |
| `/jobs` | Job listing browser with NL filter |
| `/jobs/[id]` | Job detail — match breakdown, gap analysis, artifact generation |
| `/documents` | Resume and cover letter artifact library |
| `/apply-queue` | Review queue — approve / reject queued applications |
| `/settings` | Profile fields and autopilot configuration |
| `/admin/evals` | Eval run list |
| `/admin/evals/[id]` | Eval run detail — per-case assertion results |

Stack: Next.js 15 · React 19 · Tailwind v4 · shadcn/ui · App Router.

---

## 9. Phase Status

| Phase | Description | Status |
|---|---|---|
| 0 | Project skeleton — monorepo, Docker, Next.js scaffolding | Done |
| 1 | Experience corpus + LLM client abstraction | Done |
| 2 | Multi-source scraper + structured extractor | Done |
| 3 | Two-stage matcher (embeddings + LLM-as-judge) | Done |
| 4 | Grounded resume + cover letter generator | Done |
| 5 | Eval suite + prompt versioning | Done |
| 6 | Auto-apply engine (field-mapper, gate, answer bank) | Done |
| 7 | Application pipeline + observability (arq worker, cost tracking) | Done |
| 8 | Email status sync (read-only OAuth, match→classify→gate pipeline, status events, SSE, eval suite) | Implemented |
