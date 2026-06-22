# JobCraft — Design Specification

**Date:** 2026-06-22
**Status:** Draft v1
**Author:** Bruce Ong

---

## 1. Overview

### 1.1 What JobCraft Is

JobCraft is an AI-powered job targeting and resume optimization system. Given a user's experience corpus and a set of job preferences (filters or natural language description), it:

1. Scrapes job listings from multiple sources
2. Analyzes each job description to extract required skills, seniority, and culture signals
3. Scores the user's existing experience against each job
4. Identifies skill gaps and surfaces actionable insights
5. Generates a tailored resume and cover letter for each role
6. Tracks applications through a pipeline dashboard
7. (Optional, manual) Assists with — not automates — application submission

### 1.2 What JobCraft Is Not

- **Not a fully automated submitter.** Auto-submission is ethically gray and often violates ToS. JobCraft generates artifacts and prepares applications, but the user reviews and submits.
- **Not a job board.** It aggregates from existing sources; it does not host listings.
- **Not a general-purpose resume builder.** It is a *targeted* resume optimizer — every output is for a specific job.

### 1.3 Why This Project Exists

Two parallel goals:

1. **Personal utility:** Solve the painful, repetitive problem of tailoring resumes for AI/FDE roles.
2. **Portfolio depth:** Demonstrate end-to-end production-grade AI engineering — RAG, structured extraction, LLM-as-judge, agentic workflows, evals, prompt versioning, observability — in a single coherent system.

### 1.4 Success Criteria

- User can describe a job in natural language and get a curated list of 10+ matching jobs within 2 minutes.
- User can generate a tailored resume + cover letter for any job in under 30 seconds.
- The system surfaces 3+ concrete skill gaps per job that the user can act on.
- All AI-generated artifacts are reproducible: same job + same user corpus + same prompt version = same output (modulo LLM temperature).
- The eval suite proves resume quality across at least 50 test cases.

---

## 2. High-Level Architecture

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Frontend                            │
│                    (Next.js + React + Tailwind)                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │ REST / SSE
┌────────────────────────────────▼────────────────────────────────┐
│                      Backend API Server                         │
│                  (Python FastAPI + Pydantic)                    │
└──┬───────────┬───────────┬───────────┬───────────┬──────────────┘
   │           │           │           │           │
┌──▼──┐  ┌────▼────┐  ┌───▼────┐  ┌──▼───┐  ┌────▼─────┐
│Scra-│  │Extract- │  │Match-  │  │Gener-│  │Eval      │
│per  │  │or       │  │er      │  │ator  │  │Runner    │
└──┬──┘  └────┬────┘  └───┬────┘  └──┬───┘  └────┬─────┘
   │          │           │          │            │
   │          └───┬───┬───┘          │            │
   │              │   │              │            │
┌──▼──────────────▼───▼──────────────▼────────────▼─────┐
│              Storage Layer                            │
│  Postgres (jobs, applications, prompts, runs)         │
│  Qdrant (embeddings: user experience corpus, JDs)     │
│  Filesystem (generated resumes, cover letters)        │
└───────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                     Observability Layer                         │
│         Structured logs + LLM call traces (custom)              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility |
|---|---|
| **Scraper** | Fetch job listings from configured sources. Multi-source, rate-limited, deduplicated. |
| **Extractor** | Parse raw HTML/text into structured `JobPosting` records using LLM structured outputs. |
| **Matcher** | Score user fit against a `JobPosting`. Uses embeddings + LLM-as-judge. |
| **Generator** | Produce tailored resume + cover letter Markdown + PDF for a job. RAG-driven. |
| **Eval Runner** | Run prompt suites against historical jobs to measure quality, track regression. |
| **Storage Layer** | Postgres for relational state, Qdrant for vector search, filesystem for artifacts. |
| **Observability** | Capture every LLM call (input, output, model, latency, cost) for debugging and analysis. |

### 2.3 Key Design Principles

- **LLM-agnostic.** All LLM calls go through an `LLMClient` abstraction. Swapping Anthropic ↔ OpenAI ↔ local model is a config change.
- **Reproducible runs.** Every generation is tied to a `prompt_version_id` and a `corpus_snapshot_id`. You can always re-run and explain why something was generated.
- **Async by default.** Job scraping and generation are I/O bound — everything uses `asyncio`.
- **Observable from day one.** Don't bolt on logging later. Every LLM call is logged with full context.
- **Boundary clarity.** Each component has a typed interface. No component reaches into another's internals.

---

## 3. Data Model

### 3.1 Postgres Schema

```sql
-- User profile and experience corpus
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Raw experience items — bullets, projects, education, skills
-- This is the canonical source of truth for what the user can claim
CREATE TABLE experience_items (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('work', 'project', 'education', 'skill', 'achievement')),
  title TEXT,                    -- e.g., "Software Engineer at Traveloka"
  organization TEXT,             -- e.g., "Traveloka"
  start_date DATE,
  end_date DATE,                 -- NULL = present
  content TEXT NOT NULL,         -- The actual bullet/description
  tags TEXT[] DEFAULT '{}',      -- ['typescript', 'react', 'b2c']
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scraped jobs
CREATE TABLE job_postings (
  id UUID PRIMARY KEY,
  source TEXT NOT NULL,          -- 'linkedin', 'greenhouse', 'lever', 'wellfound'
  source_url TEXT NOT NULL,
  source_id TEXT,                -- Source's own ID, for dedup
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  remote_policy TEXT,            -- 'remote', 'hybrid', 'onsite'
  raw_content TEXT NOT NULL,     -- Original scraped HTML/text
  extracted JSONB,               -- Structured extraction result
  scraped_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (source, source_id)
);

-- Match scores between a user and a job
CREATE TABLE matches (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  job_id UUID NOT NULL REFERENCES job_postings(id),
  overall_score FLOAT NOT NULL,  -- 0..1
  dimension_scores JSONB NOT NULL, -- {skills: 0.8, seniority: 0.9, ...}
  gaps JSONB NOT NULL,           -- [{skill: 'kubernetes', severity: 'high'}, ...]
  rationale TEXT NOT NULL,
  prompt_version_id UUID NOT NULL,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, job_id, prompt_version_id)
);

-- Generated artifacts (resumes, cover letters)
CREATE TABLE artifacts (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  job_id UUID NOT NULL REFERENCES job_postings(id),
  kind TEXT NOT NULL CHECK (kind IN ('resume', 'cover_letter')),
  format TEXT NOT NULL CHECK (format IN ('markdown', 'pdf', 'html')),
  content TEXT NOT NULL,         -- Or filesystem path for PDF
  prompt_version_id UUID NOT NULL,
  generation_run_id UUID NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Application pipeline tracking
CREATE TABLE applications (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  job_id UUID NOT NULL REFERENCES job_postings(id),
  status TEXT NOT NULL CHECK (status IN (
    'interested', 'preparing', 'submitted', 'phone_screen',
    'technical', 'onsite', 'offer', 'rejected', 'withdrawn'
  )),
  notes TEXT,
  resume_artifact_id UUID REFERENCES artifacts(id),
  cover_letter_artifact_id UUID REFERENCES artifacts(id),
  submitted_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prompt versioning — every prompt has a stable identifier
CREATE TABLE prompt_versions (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,            -- 'extract_job', 'generate_resume'
  version INT NOT NULL,          -- 1, 2, 3...
  template TEXT NOT NULL,        -- The prompt template
  model TEXT NOT NULL,           -- 'claude-3-5-sonnet-20241022'
  temperature FLOAT NOT NULL,
  metadata JSONB DEFAULT '{}',   -- max_tokens, response_format, etc.
  is_active BOOLEAN DEFAULT FALSE, -- Only one active version per name
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (name, version)
);
CREATE UNIQUE INDEX one_active_per_name ON prompt_versions (name) WHERE is_active = TRUE;

-- Every LLM call is logged here for observability
CREATE TABLE llm_calls (
  id UUID PRIMARY KEY,
  prompt_version_id UUID NOT NULL REFERENCES prompt_versions(id),
  inputs JSONB NOT NULL,         -- The variables substituted into the template
  rendered_prompt TEXT NOT NULL, -- Final prompt sent
  response TEXT NOT NULL,        -- Raw model response
  parsed_response JSONB,         -- Structured parse, if applicable
  model TEXT NOT NULL,
  input_tokens INT,
  output_tokens INT,
  latency_ms INT,
  cost_usd NUMERIC(10, 6),
  error TEXT,
  called_at TIMESTAMPTZ DEFAULT NOW()
);

-- Eval suite runs
CREATE TABLE eval_runs (
  id UUID PRIMARY KEY,
  suite_name TEXT NOT NULL,      -- 'resume_quality_v1'
  prompt_version_id UUID NOT NULL REFERENCES prompt_versions(id),
  results JSONB NOT NULL,        -- Per-test results
  aggregate_scores JSONB NOT NULL, -- Overall metrics
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);
```

### 3.2 Vector Store (Qdrant)

Two collections:

| Collection | Vector source | Used for |
|---|---|---|
| `user_experience` | Embedded `experience_items.content` per user | Resume generation RAG, gap detection |
| `job_postings` | Embedded JD `description` + `requirements` | Semantic job search, similar-job retrieval |

Both collections use OpenAI `text-embedding-3-small` (1536 dim) by default. Embedding model is configurable.

### 3.3 Filesystem Layout

```
data/
  artifacts/
    <user_id>/
      <job_id>/
        resume-<artifact_id>.md
        resume-<artifact_id>.pdf
        cover-letter-<artifact_id>.md
        cover-letter-<artifact_id>.pdf
  scraped_raw/
    <source>/<date>/<source_id>.html  # For debugging extraction
```

---

## 4. Component Specifications

### 4.1 Scraper

**Purpose:** Fetch job listings from multiple sources reliably.

**Sources (priority order):**
1. **Greenhouse** — many AI companies (Anthropic, OpenAI use Greenhouse). Well-structured HTML, easy to parse.
2. **Lever** — also common for AI startups. Similar structure to Greenhouse.
3. **Wellfound (AngelList)** — startup-focused, good for FDE roles at smaller companies.
4. **LinkedIn** — high coverage but harder to scrape; defer to v2.

**Design:**
- Each source has its own adapter implementing `JobSource` protocol:
  ```python
  class JobSource(Protocol):
      name: str
      async def list_jobs(self, filters: JobFilters) -> AsyncIterator[RawJobPosting]: ...
      async def fetch_job(self, source_id: str) -> RawJobPosting: ...
  ```
- Scrapers respect `robots.txt` and rate limit themselves.
- Deduplication on `(source, source_id)` and a content-hash fallback.
- Storage: raw HTML/text → `data/scraped_raw/`, parsed → `job_postings` table.

**Filters:**
```python
class JobFilters(BaseModel):
    keywords: list[str] = []        # ["forward deployed", "AI engineer"]
    companies: list[str] | None = None
    locations: list[str] | None = None
    remote_only: bool = False
    seniority: list[Literal["junior", "mid", "senior", "staff"]] | None = None
    posted_within_days: int = 30
```

**Natural language → filters:** Optional LLM step that converts `"FDE roles at AI labs, remote or SF, mid-senior"` into a `JobFilters` object via structured output. This is a small, clean place to demonstrate structured extraction.

**Resilience:**
- Each scrape run produces a structured log: `source, total_listed, total_fetched, total_failed, total_new`.
- Failures don't crash the run — they're logged and the scraper continues.

### 4.2 Extractor

**Purpose:** Convert raw scraped content into a typed `JobPosting` record.

**Output schema:**
```python
class ExtractedJob(BaseModel):
    company: str
    title: str
    seniority: Literal["junior", "mid", "senior", "staff", "principal"] | None
    location: str | None
    remote_policy: Literal["remote", "hybrid", "onsite"] | None
    salary_min_usd: int | None
    salary_max_usd: int | None
    required_skills: list[str]      # Must-haves
    preferred_skills: list[str]     # Nice-to-haves
    responsibilities: list[str]
    qualifications: list[str]
    culture_signals: list[str]      # Free-form: "values move-fast", "research-oriented"
    summary: str                    # 2-3 sentence summary for UI display
```

**Implementation:**
- Use Anthropic / OpenAI structured outputs (JSON mode + Pydantic).
- Prompt template lives in `prompts/extract_job/v1.txt`, registered as a `prompt_version`.
- Failure handling: if parse fails, log to `llm_calls.error`, retry once with a "fix this JSON" follow-up, then give up and mark `extracted = null`.

### 4.3 Matcher

**Purpose:** Score how well the user's experience matches a job.

**Two-stage matching:**

1. **Embedding-based prefilter.** Compute cosine similarity between the JD embedding and the user's full corpus centroid (or top-k experience items). Cheap, fast, runs on every job.

2. **LLM-as-judge deep scoring** (only for top-N from stage 1). Sends the structured JD + relevant user experience items to an LLM with a scoring rubric:
   ```
   For each dimension (skills, seniority, domain, culture), score 0..1
   with rationale. Identify top 3 gaps with severity.
   ```

**Output:**
```python
class MatchResult(BaseModel):
    overall_score: float  # 0..1
    dimension_scores: dict[str, float]  # {"skills": 0.8, "seniority": 0.9, ...}
    gaps: list[Gap]  # [{skill: "kubernetes", severity: "high", rationale: "..."}]
    rationale: str
    matched_experiences: list[UUID]  # Which experience_items most support this match
```

**Why two stages:** Demonstrates understanding of cost-vs-quality tradeoffs. Stage 1 is cheap embeddings, stage 2 is expensive LLM-as-judge. Real FDE work has the same shape.

### 4.4 Generator

**Purpose:** Produce a tailored resume and cover letter for a specific job.

**Resume generation flow:**

```
1. Load user's experience corpus
2. Load extracted job (required skills, responsibilities, culture)
3. RAG: retrieve top-N experience items relevant to this job (vector search)
4. LLM call (resume_generation_v1):
   - System: "You write resumes. Use only facts from <experience>. 
              Tailor framing to <job>. Return Markdown."
   - User: experience items + job + style preferences
5. Validate output:
   - All claims trace back to experience items (LLM-as-judge check)
   - Length within bounds
   - No invented facts
6. Render to PDF via WeasyPrint or Typst
7. Store as artifact, link to user + job
```

**Cover letter generation flow:** Similar, but with explicit emphasis on:
- Why this company specifically (uses culture signals from extraction)
- Why this role specifically (uses responsibilities)
- One concrete story from the user's experience corpus that maps to the JD

**Anti-hallucination strategy:**
- Generator is *strictly* grounded in the experience corpus. The prompt explicitly forbids invention.
- A separate `groundedness_check` prompt (LLM-as-judge) runs after generation. Each claim in the resume must map to an experience item ID.
- Failures surface in the UI: "I generated this bullet but couldn't ground it in your corpus — review or remove."

**Style controls:**
```python
class StyleConfig(BaseModel):
    tone: Literal["formal", "balanced", "punchy"] = "balanced"
    length: Literal["one_page", "two_page"] = "one_page"
    emphasis: list[str] = []  # e.g., ["leadership", "AI work"]
```

### 4.5 Eval Runner

**Purpose:** Prove that generation and matching prompts work, and catch regressions when prompts change.

**Test case structure:**
```yaml
# eval_suites/resume_quality_v1.yaml
name: resume_quality_v1
description: Validates resume generation quality
cases:
  - id: case_001
    user_corpus: fixtures/user_bruce.json
    job: fixtures/jobs/anthropic_fde.json
    assertions:
      - kind: contains_skill
        skill: "AI"
      - kind: groundedness
        threshold: 1.0  # 100% of claims must be grounded
      - kind: llm_judge
        rubric: rubrics/resume_quality.txt
        threshold: 0.7
      - kind: length
        min_words: 350
        max_words: 700
```

**Assertion kinds:**
- `contains_skill`, `excludes_phrase`, `length` — deterministic
- `groundedness` — runs LLM-as-judge to check every claim against corpus
- `llm_judge` — runs a rubric-based score

**Runner behavior:**
- Runs all cases in parallel (asyncio).
- Outputs structured results per case + aggregate scores.
- Stores in `eval_runs` table.
- CLI: `jobcraft eval run resume_quality_v1 --prompt-version=resume_generation_v1`
- CI integration: fail build if scores drop below baseline.

### 4.6 LLM Client Abstraction

**Single point of LLM access. All other components call this.**

```python
class LLMClient:
    async def complete(
        self,
        prompt_version_id: UUID,
        inputs: dict,
        response_model: type[T] | None = None,  # Pydantic model for structured
    ) -> LLMResponse[T]:
        """
        Renders prompt template, calls model, parses response,
        logs to llm_calls table, returns typed result.
        """
```

**Why a single abstraction:**
- Every LLM call is automatically logged.
- Provider swap is trivial.
- Cost tracking is unified.
- Retry/fallback logic lives in one place.
- Eval runner can replay historical calls.

**Provider adapters:**
- `AnthropicAdapter` — primary
- `OpenAIAdapter` — fallback / comparison
- `MockAdapter` — for tests; returns fixtures

### 4.7 Observability

**Every LLM call is logged with:**
- Prompt version ID, full rendered prompt, response
- Model, tokens, latency, cost
- Caller context (which component, which job, which user)
- Error details if it failed

**A simple `/admin/calls` dashboard page** lets you:
- Filter by prompt version, model, time range
- See cost per day, average latency
- Drill into individual calls (full prompt + response)
- Compare two runs of the same prompt version on the same input

This is genuinely useful operationally *and* a great interview talking point.

---

## 5. API Surface

### 5.1 REST Endpoints

```
POST   /api/users                          Create user
GET    /api/users/me

POST   /api/experience                     Add experience item
GET    /api/experience
PUT    /api/experience/{id}
DELETE /api/experience/{id}
POST   /api/experience/import              Bulk import from JSON / resume PDF

POST   /api/scrape                         Trigger scrape with filters
       body: {filters} or {natural_language: "FDE roles at AI labs"}
GET    /api/scrape/runs/{run_id}

GET    /api/jobs                           List jobs (paginated, filterable)
GET    /api/jobs/{id}

POST   /api/match                          Compute match for (user, job)
GET    /api/match?job_id=...

POST   /api/generate                       Generate resume + cover letter
       body: {job_id, style_config}
       returns: {resume_artifact_id, cover_letter_artifact_id}
GET    /api/artifacts/{id}                 Download artifact

POST   /api/applications                   Create application entry
PATCH  /api/applications/{id}              Update status
GET    /api/applications                   Pipeline view

POST   /api/eval/run                       Trigger eval suite
GET    /api/eval/runs/{id}
```

### 5.2 SSE Streaming

Long-running operations stream progress:
- `/api/scrape` — streams per-source progress
- `/api/generate` — streams generation tokens for UX
- `/api/eval/run` — streams per-case results

---

## 6. Frontend

### 6.1 Pages

| Route | Purpose |
|---|---|
| `/` | Dashboard — pipeline overview, recent jobs |
| `/experience` | Manage experience corpus |
| `/jobs` | Browse + search scraped jobs |
| `/jobs/[id]` | Job detail: extracted info, match score, gaps, generate button |
| `/applications` | Kanban-style pipeline |
| `/admin/prompts` | View prompt versions, diff between versions |
| `/admin/calls` | LLM call inspector |
| `/admin/evals` | Eval suite runs and trends |

### 6.2 Key UX Flows

**Flow 1 — Bootstrap:**
1. User uploads existing resume PDF → LLM extracts experience items → user reviews/edits.
2. User triggers initial scrape with a natural language query.
3. User sees ranked job list with match scores.

**Flow 2 — Apply to a job:**
1. User clicks a job → sees extracted info, match score, gaps.
2. User clicks "Generate" → resume + cover letter stream in.
3. User reviews, edits inline, exports PDF.
4. User clicks "Mark as Submitted" → application tracked.

**Flow 3 — Iterate prompts:**
1. Developer edits a prompt template → registers as new `prompt_version`.
2. Runs eval suite on new version.
3. Reviews diff vs previous version in `/admin/prompts`.
4. Promotes new version to default if eval scores improved.

---

## 7. Technical Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend language | Python 3.12 | Best LLM ecosystem; async via `asyncio` |
| Web framework | FastAPI | Async, Pydantic-native, OpenAPI for free |
| Frontend | Next.js 15 + React 19 + Tailwind | Mainstream; user already knows this |
| Database | Postgres 16 | Reliable, JSONB for flexibility |
| Vector store | Qdrant | Local-first, open source, easy Docker deploy |
| LLM SDKs | `anthropic`, `openai` | Official SDKs |
| PDF rendering | Typst | Cleaner output than WeasyPrint; LLM-friendly markup |
| Scraping | `httpx` + `selectolax` + `playwright` (fallback) | Async; Playwright only when JS-rendered |
| Job queue | `arq` (Redis-backed) | Async-first, lightweight |
| ORM | SQLAlchemy 2.x + Alembic | Standard, reliable |
| Testing | `pytest` + `pytest-asyncio` + `vcrpy` | VCR cassettes capture LLM responses |
| Deployment | Docker Compose locally; Fly.io / Railway for hosted | Single-binary feel via compose |

---

## 8. Implementation Phases

The spec is large. Implementation will be phased so each phase is independently demoable.

### Phase 0 — Project skeleton (1 day with AI assist)
- Monorepo layout (`backend/`, `frontend/`, `eval/`, `docs/`)
- Docker Compose for Postgres + Qdrant
- FastAPI hello-world
- Next.js scaffolded
- CI: lint + type check

### Phase 1 — Experience corpus + LLM client (2 days)
- `users`, `experience_items`, `prompt_versions`, `llm_calls` tables
- `LLMClient` with Anthropic + Mock adapters
- Resume PDF import (LLM extraction)
- Experience CRUD UI
- **Demo:** Upload your existing resume, see structured experience items.

### Phase 2 — Scraper + Extractor (2 days)
- Greenhouse + Lever adapters
- Natural-language → JobFilters
- Extractor with structured output
- Jobs list UI
- **Demo:** Scrape Anthropic + OpenAI Greenhouse boards, see extracted JDs.

### Phase 3 — Matcher (2 days)
- Embedding pipeline (Qdrant integration)
- Two-stage matcher (embedding prefilter + LLM judge)
- Match results on job detail page
- **Demo:** See match scores + gaps for every scraped job.

### Phase 4 — Generator (3 days)
- Resume + cover letter generation prompts
- Groundedness check
- Typst → PDF pipeline
- Generation UI with streaming
- **Demo:** Generate tailored resume for an Anthropic FDE listing.

### Phase 5 — Eval suite (2 days)
- YAML test case loader
- Assertion runners (deterministic + LLM-judge)
- Eval CLI + admin dashboard
- Initial eval suites: `resume_quality_v1`, `extraction_accuracy_v1`, `match_consistency_v1`
- **Demo:** Run eval suite, see per-prompt-version score history.

### Phase 6 — Application pipeline + polish (2 days)
- Applications table + Kanban UI
- Admin/observability pages
- Cost dashboard
- README + architecture doc

**Total estimated effort:** ~14 working days with aggressive AI assistance. With a 2-3 week focused sprint as you described, this fits.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Scraping breaks when sites change | Multi-source design; each source independent; fallback to manual JD paste |
| LLM costs spiral | All calls logged with cost; daily budget alarm; cheap models (Haiku) for prefiltering |
| Resume generation hallucinates | Strict groundedness check; LLM-as-judge gate; UI flags ungrounded claims |
| Job sites detect/block scrapers | Respect rate limits + robots.txt; rotate user agents; defer LinkedIn to v2 |
| Spec is too large to finish in one sprint | Phased plan — each phase is independently useful |
| Interview-related risk: "did AI write all this?" | The eval suite + observability + prompt versioning are deeply your engineering work and impossible to fake credibly. Lean on those in interviews. |

---

## 10. Out of Scope (v1)

- Auto-submission of applications
- Browser extension integrations
- Multi-user accounts with auth (single-user MVP)
- Mobile UI
- LinkedIn scraping (deferred)
- Fine-tuning custom models
- Multi-language resumes
- Job recommendation based on past application outcomes (great v2 feature)

---

## 11. What This Project Demonstrates for FDE Interviews

| Concept | Where It Shows Up |
|---|---|
| **RAG** | Experience corpus → resume generation; semantic job search |
| **Structured outputs** | Job extraction; match scoring; filter parsing |
| **LLM-as-judge** | Match scoring; groundedness check; eval rubrics |
| **Evals & regression testing** | Entire `eval/` subsystem |
| **Prompt engineering & versioning** | `prompt_versions` table; admin diff view |
| **Tool use / agentic workflows** | Scrape → extract → match → generate chain |
| **Observability for AI systems** | `llm_calls` table; admin dashboard |
| **Cost/quality tradeoffs** | Two-stage matcher; per-call cost tracking |
| **Production engineering** | Async, typed APIs, migrations, eval CI |
| **Customer-facing thinking** | The whole UX is built around a real user (you), with grounding/uncertainty surfaced honestly |

This is the project we want on the resume. It's not a chatbot wrapper. It's an end-to-end AI system with the same architectural concerns Anthropic and OpenAI think about every day for their enterprise deployments.
