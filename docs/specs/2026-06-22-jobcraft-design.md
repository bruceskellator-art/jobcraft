# JobCraft — Design Specification

**Date:** 2026-06-24
**Status:** Draft v2
**Author:** Bruce Ong

---

## 1. Overview

### 1.1 What JobCraft Is

JobCraft is an AI-powered job targeting and resume optimization system. Given a user's experience corpus and a set of job preferences (filters or natural language description), it:

1. Scrapes job listings from multiple sources (Singapore-focused: MyCareersFuture, ATS boards, LinkedIn, regional tech boards)
2. Analyzes each job description to extract required skills, seniority, and culture signals
3. Scores the user's existing experience against each job
4. Identifies skill gaps and surfaces actionable insights
5. Generates a tailored resume and cover letter for each role
6. **Auto-applies at scale** — fills application forms with an LLM field-mapping agent, auto-submits where it is confident and safe, and queues the rest for fast batch review
7. Tracks applications through a pipeline dashboard
8. **Auto-syncs application status from email** *(v2)* — connects to the user's inbox (read-only), matches recruiter emails to applications, and uses an LLM classifier to advance the pipeline (acknowledged → screen → interview → offer / rejected) so the board stays current without manual dragging

### 1.2 What JobCraft Is Not

- **Not a spray-and-pray spammer.** Auto-apply is a *first-class* feature, but every application is still tailored (grounded resume + cover letter per role) and gated by a fit threshold. Volume comes from automation, not from lowering quality.
- **Not a CAPTCHA farm or a ToS-evasion tool.** JobCraft does not solve CAPTCHAs or defeat bot-detection. Where a site hard-blocks automation, the application falls back to the human review queue. See §9 for the ToS/account-risk posture.
- **Not a job board.** It aggregates from existing sources; it does not host listings.
- **Not a general-purpose resume builder.** It is a *targeted* resume optimizer — every output is for a specific job.

> **Single-user, personal-use tool.** JobCraft applies to jobs *on behalf of its own operator*, using the operator's own accounts, credentials, and truthful profile data. It is not a service that applies on behalf of third parties.

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
- The user can queue 100+ tailored applications and clear the entire review queue in under 15 minutes, with the safe majority auto-submitted and only ambiguous applications surfaced.
- No application is ever submitted with an invented answer to a knockout question (work authorization, visa status, years of experience).

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
| **Apply Engine** | Drive application forms via browser automation. LLM field-mapping agent fills fields from the profile + answer bank + generated artifacts; a confidence gate auto-submits safe/high-confidence applications and queues the rest for review. Rate-limited per source. |
| **Email Status Tracker** *(v2)* | Connect to the user's inbox read-only; match recruiter emails to applications; LLM-classify each into a status event and advance the pipeline (with a confirmation step for low-confidence transitions). |
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
  source TEXT NOT NULL,          -- 'mycareersfuture', 'greenhouse', 'lever', 'ashby', 'linkedin', 'glints', 'nodeflair', 'serpapi'
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
  job_id UUID REFERENCES job_postings(id),  -- NULL for the uploaded baseline résumé
  kind TEXT NOT NULL CHECK (kind IN ('resume', 'cover_letter')),
  format TEXT NOT NULL CHECK (format IN ('markdown', 'pdf', 'html')),
  content TEXT NOT NULL,         -- Or filesystem path for PDF
  is_baseline BOOLEAN DEFAULT FALSE, -- the user's uploaded résumé; the "before" baseline
  scores JSONB,                  -- per-criteria scores, e.g. {fit, groundedness, ats_keywords, quantified_impact, clarity} each 0..1
  prompt_version_id UUID,        -- NULL for the uploaded baseline
  generation_run_id UUID,        -- NULL for the uploaded baseline
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Application pipeline tracking
CREATE TABLE applications (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  job_id UUID NOT NULL REFERENCES job_postings(id),
  status TEXT NOT NULL CHECK (status IN (
    -- discovery + auto-apply lifecycle
    'interested', 'queued', 'auto_filling', 'needs_review', 'submitted',
    'blocked', 'failed',
    -- post-submission pipeline
    'phone_screen', 'technical', 'onsite', 'offer', 'rejected', 'withdrawn'
  )),
  apply_mode TEXT CHECK (apply_mode IN ('auto', 'assisted', 'manual')),
  apply_confidence FLOAT,        -- 0..1 from the field-mapping agent
  blocked_reason TEXT,           -- 'captcha', 'login_required', 'unknown_question', ...
  notes TEXT,
  resume_artifact_id UUID REFERENCES artifacts(id),
  cover_letter_artifact_id UUID REFERENCES artifacts(id),
  submitted_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reusable profile fields used to fill application forms.
-- Holds the user's TRUE answers; the agent never invents these.
CREATE TABLE profile_fields (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  key TEXT NOT NULL,             -- 'work_authorization', 'notice_period', 'salary_expectation_sgd', 'phone'
  value TEXT NOT NULL,
  is_knockout BOOLEAN DEFAULT FALSE, -- work auth / visa / eligibility: pinned, never auto-guessed
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, key)
);

-- Answer bank: reusable answers to free-text screening questions.
-- Drafts are LLM-generated, approved once by the user, then reused by similarity.
CREATE TABLE answer_bank (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  question TEXT NOT NULL,        -- canonical screening question
  answer TEXT NOT NULL,
  approved BOOLEAN DEFAULT FALSE, -- only approved answers may be auto-submitted
  reuse_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- Embedded in Qdrant (collection `answer_bank`) for similarity reuse across forms.

-- One row per attempt to apply to a job (auditable, replayable).
CREATE TABLE application_attempts (
  id UUID PRIMARY KEY,
  application_id UUID NOT NULL REFERENCES applications(id),
  strategy TEXT NOT NULL,        -- 'linkedin_easy_apply', 'greenhouse_form', 'mycareersfuture', 'generic_form'
  field_map JSONB NOT NULL,      -- [{field, value, source, confidence}]
  overall_confidence FLOAT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('submitted', 'queued', 'blocked', 'failed')),
  blocked_reason TEXT,
  screenshot_path TEXT,          -- evidence of submitted/blocked state
  attempted_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Email status sync (v2) ──────────────────────────────────────────
-- A connected inbox. Tokens are stored ENCRYPTED, never plaintext.
CREATE TABLE email_accounts (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id),
  provider TEXT NOT NULL CHECK (provider IN ('gmail', 'outlook')),
  email_address TEXT NOT NULL,
  oauth_token_enc BYTEA NOT NULL,   -- encrypted refresh/access token bundle
  scopes TEXT[] NOT NULL,           -- read-only scopes only, e.g. gmail.readonly
  sync_cursor TEXT,                 -- Gmail historyId / Graph deltaLink for incremental sync
  watch_expires_at TIMESTAMPTZ,     -- Gmail watch / Graph subscription expiry (renew before)
  connected_at TIMESTAMPTZ DEFAULT NOW(),
  last_synced_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'reauth_required', 'revoked')),
  UNIQUE (user_id, email_address)
);

-- A recruiter/company email we matched to an application. We store metadata +
-- a redacted snippet for the audit trail, not the full mailbox.
CREATE TABLE email_messages (
  id UUID PRIMARY KEY,
  email_account_id UUID NOT NULL REFERENCES email_accounts(id),
  application_id UUID REFERENCES applications(id), -- NULL until matched
  provider_message_id TEXT NOT NULL,  -- Gmail/Graph message id (idempotency)
  thread_id TEXT,
  from_address TEXT NOT NULL,
  from_domain TEXT NOT NULL,          -- matched against the application's company domain
  subject TEXT,
  snippet TEXT,                       -- short preview only; full body fetched transiently, not persisted
  received_at TIMESTAMPTZ NOT NULL,
  match_method TEXT,                  -- 'domain', 'thread', 'ats_sender', 'llm'
  match_confidence FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (email_account_id, provider_message_id)
);

-- An inferred status transition proposed (or applied) from an email.
-- Low-confidence transitions require user confirmation before they touch the app.
CREATE TABLE status_events (
  id UUID PRIMARY KEY,
  application_id UUID NOT NULL REFERENCES applications(id),
  email_message_id UUID REFERENCES email_messages(id), -- source; NULL if manual
  from_status TEXT,
  to_status TEXT NOT NULL,            -- one of applications.status values
  classification TEXT NOT NULL,       -- 'acknowledged','assessment','phone_screen','technical','onsite','offer','rejected','ghosted_followup','other'
  confidence FLOAT NOT NULL,
  state TEXT NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'applied', 'dismissed')),
  prompt_version_id UUID REFERENCES prompt_versions(id), -- the classifier prompt
  created_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX status_events_pending ON status_events (application_id) WHERE state = 'proposed';

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
| `answer_bank` | Embedded screening `question` per user | Reuse approved answers across application forms by similarity |

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

**Sources (Singapore-focused, priority order):**

*Tier 1 — compliant, structured, reliable (the foundation; the app always works on these):*
1. **MyCareersFuture.gov.sg** — Singapore government (Workforce Singapore) portal. Best SG coverage, free JSON API (`api.mycareersfuture.gov.sg`), no auth, structured. The primary SG source.
2. **Greenhouse / Lever / Ashby** — official public job-board JSON APIs. Covers most tech companies hiring in SG (Stripe, ByteDance, etc.). No scraping — documented endpoints.

*Tier 2 — best-effort, high value, expect breakage (never the foundation):*
3. **LinkedIn** — excellent SG coverage. Scraped via Playwright using a **dedicated, disposable** logged-in session at low rate. Violates LinkedIn ToS and the account may be restricted — treated as a bonus adapter that is expected to break and rotate, never a dependency. See §9.
4. **Glints / NodeFlair** — SEA / SG tech-focused boards.

*Tier 3 — optional, paid aggregator:*
5. **SerpAPI (Google Jobs endpoint)** — returns the "Google for Jobs" results as clean JSON (Google itself offers no free jobs API; its old Cloud Talent Solution search was discontinued). Paid; enable if Tier 1–2 coverage is insufficient.

> **Note on Adzuna and global aggregators:** evaluated and **dropped for SG** — their Singapore coverage is thin. SG coverage comes from MyCareersFuture + LinkedIn + ATS boards instead.

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

**Artifact scoring & baseline comparison.** Every generated résumé/cover letter is
scored across a fixed rubric and stored on `artifacts.scores`:

```python
class ArtifactScores(BaseModel):
    fit: float               # alignment to this job's requirements (reuses match)
    groundedness: float      # share of claims traceable to experience items
    ats_keywords: float      # coverage of the JD's required keywords
    quantified_impact: float # share of bullets with concrete/measured outcomes
    clarity: float           # readability / length discipline
```

The user's **uploaded résumé is stored as a baseline artifact** (`is_baseline = true`,
`job_id = NULL`) and scored on the same rubric, so the **Documents** view shows
before → after improvement per criterion (the `vs baseline` delta). This makes the
value of the tool measurable and is a concrete demo artifact.

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

### 4.8 Apply Engine

**Purpose:** Eliminate the hours of manual clicking. Apply to many jobs through a
single review surface — the user never touches a job board's UI. This is the
feature the product is organized around.

**The problem shape.** Applications are web forms of varying difficulty:

| Tier | Example | Automatable? |
|---|---|---|
| 1-click / Easy Apply | LinkedIn Easy Apply, some MyCareersFuture | Yes — short modal |
| Known ATS templates | Greenhouse, Lever, Ashby hosted forms | Yes — predictable fields |
| Arbitrary career pages | Bespoke company forms | Mostly — each differs |
| Enterprise ATS | Workday, Taleo, iCIMS | Painful → `assisted` |
| CAPTCHA-gated | reCAPTCHA, bot walls | No → `blocked`, hard stop |

**Three parts:**

1. **Browser automation (Playwright).** Drives a real browser per application,
   using the user's own logged-in session for sites that require it. Rate-limited
   per source (applying to hundreds in minutes is itself a ban signal).

2. **LLM field-mapping agent.** The portfolio-worthy core:
   ```
   For each queued application:
     1. Render the form → extract fields (labels, types, options)
     2. LLM maps each field → value, drawing from:
          • profile_fields   (name, email, phone, work auth, notice, salary)
          • answer_bank       (approved reusable screening answers, by similarity)
          • the tailored cover letter / corpus (free-text "why this role")
     3. Attach the generated resume + cover letter PDF
     4. Emit per-field + overall confidence
   ```

3. **Confidence gate.** Decides per application:
   - **Auto-submit** when confidence is high AND the form is safe (Easy Apply,
     known ATS, no unresolved knockout question).
   - **Queue for review** otherwise (unknown screening question, low confidence,
     enterprise ATS) → surfaces in the Apply Queue as a uniform field-map card.
   - **Block** on CAPTCHA / bot-detection → never bypassed; routed to manual.

**Autopilot config (per source, user-controlled):**
```python
class AutopilotConfig(BaseModel):
    mode: Literal["off", "selective", "full"] = "selective"
    auto_submit_sources: list[str] = ["linkedin_easy_apply", "mycareersfuture"]
    min_confidence: float = 0.75   # below this → review queue regardless
    min_fit: float = 0.55          # never auto-apply below this match score
    daily_cap: int = 80            # rate-limit / ban-avoidance
```

**`ApplyStrategy` protocol** (one adapter per platform, parallels `JobSource`):
```python
class ApplyStrategy(Protocol):
    name: str
    can_handle: Callable[[JobPosting], bool]
    async def fill(self, app: Application, ctx: ApplyContext) -> FieldMap: ...
    async def submit(self, app: Application, field_map: FieldMap) -> ApplyOutcome: ...
```

**Hard safety rules (enforced, not advisory):**
- **Knockout fields are pinned and never auto-filled with invented values.** Work
  authorization, visa status, citizenship, and years-of-experience come only from
  `profile_fields` (the user's true answers). If missing, the application is
  queued — never guessed. Critical in SG (work-pass questions are common and
  consequential).
- **No CAPTCHA solving.** No third-party solving services, no bot-detection
  evasion. Blocked → manual.
- **Approved answers only.** Only `answer_bank` rows the user has approved may be
  auto-submitted; unapproved drafts force review.
- **Per-source rate limits + daily cap** to avoid account bans.

**Workers** run on `arq` (Redis), already in the stack. Every attempt writes an
`application_attempts` row (field map, confidence, outcome, screenshot) for audit
and replay.

### 4.9 Email Status Tracker *(v2)*

**Purpose:** Keep the Applications board current automatically. After you apply,
recruiters reply by email — acknowledgements, screen invites, assessments,
rejections, offers. Manually dragging cards across the Kanban is exactly the kind
of repetitive work JobCraft exists to remove. This component reads those emails
and advances the pipeline for you, asking for confirmation only when unsure.

**Why this is hard (and worth speccing carefully):** there is no clean API that
says "candidate X moved to stage Y." Signal lives in unstructured email from
hundreds of different senders and ATS systems. The pipeline is therefore a
classic **noisy-source → match → classify → confirm** problem:

```
Inbox (read-only)
   │  incremental sync (Gmail historyId / Graph delta)
   ▼
1. INGEST    pull new messages since sync_cursor; store metadata + snippet
   ▼
2. MATCH     link message → application
                • company domain == application's company domain
                • thread_id continues an application's known thread
                • known ATS sender patterns (greenhouse.io, lever.co, ashbyhq.com,
                  myworkday.com, …)
                • LLM tie-break when ambiguous (multiple open apps at one company)
   ▼
3. CLASSIFY  LLM maps the email → a status classification + confidence
                (acknowledged / assessment / phone_screen / technical / onsite /
                 offer / rejected / other) — prompt-versioned like every LLM call
   ▼
4. GATE      high confidence + monotonic transition → apply automatically
             low confidence OR backwards/ambiguous → 'proposed' status_event,
             surfaced for one-tap confirm/dismiss
   ▼
5. UPDATE    write status_event; on apply, update applications.status; stream via SSE
```

**Connection & sync.**
- **OAuth, read-only.** Gmail `gmail.readonly`; Microsoft Graph `Mail.Read`. We
  never request send/modify scopes. The consent screen states exactly this.
- **Incremental, not full-scan.** First connect backfills only since the user's
  earliest `submitted_at`. Thereafter we sync deltas via Gmail `historyId` /
  Graph `deltaLink` stored in `email_accounts.sync_cursor`.
- **Push where available, poll as fallback.** Gmail `users.watch` → Pub/Sub and
  Graph subscriptions give near-real-time nudges; a periodic `arq` job (e.g. every
  15 min) is the reliable fallback and also renews `watch_expires_at`.
- **Scoped to job hunting.** We only persist messages that *match* an application.
  Everything else is looked at transiently in memory and dropped — we are not
  indexing the user's mailbox.

**Matching strategy (cheap → expensive):** deterministic first (domain, thread,
known ATS senders) resolves the large majority for free; the LLM is only invoked
to disambiguate (e.g. two open applications at the same parent company) — the same
two-stage cost discipline as the Matcher (§4.3).

**Classification output:**
```python
class EmailStatusInference(BaseModel):
    classification: Literal[
        "acknowledged", "assessment", "phone_screen", "technical",
        "onsite", "offer", "rejected", "ghosted_followup", "other"
    ]
    confidence: float                 # 0..1
    suggested_status: str             # maps to applications.status
    evidence: str                     # one quoted line that justifies it (for the UI)
    requires_human: bool              # true for offer/rejected → always confirm
```

**Confidence gate (mirrors the Apply Engine's posture):**
- **Auto-apply the transition** when confidence ≥ threshold *and* it moves the
  application forward monotonically (e.g. `submitted → phone_screen`).
- **Propose, don't apply** when confidence is low, the transition is backwards/
  skips stages, or the classification is high-stakes. `offer` and `rejected`
  **always** require a one-tap confirm — we never silently mark someone rejected.
- Every transition is reversible: a `status_event` is an auditable record, and the
  user can dismiss/undo. We never lose the email trail.

**Hard rules (privacy & safety — enforced, not advisory):**
- **Read-only scopes only.** No send, no delete, no modify — ever.
- **OAuth tokens encrypted at rest** (`email_accounts.oauth_token_enc`); never
  logged, never returned by any API. Disconnect deletes the token immediately.
- **Minimal retention.** Persist matched-message metadata + a short snippet for
  the audit trail; do not persist full bodies of unmatched mail.
- **User owns the loop.** One-click disconnect; per-account pause; a clear
  "what we can see" disclosure. This is the operator's own inbox, single-user.

**Workers:** runs on the existing `arq`/Redis queue. Each classification is a
normal `LLMClient` call (prompt-versioned, logged to `llm_calls`, eval-able) — so
status inference gets the same observability and regression testing as the rest of
the system, and can be tuned with its own eval suite (`status_classification_v1`).

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
GET    /api/artifacts                      List generated documents (+ scores, filterable by job/kind)
GET    /api/artifacts/{id}                 Download artifact
GET    /api/artifacts/{id}/scores          Per-criteria scores + delta vs baseline
POST   /api/artifacts/baseline             Upload baseline résumé (scored, used as the "before")

POST   /api/applications                   Create application entry
PATCH  /api/applications/{id}              Update status
GET    /api/applications                   Pipeline view

# Auto-apply
POST   /api/apply/queue                     Add jobs to the apply queue
       body: {job_ids: [...]} or {filter: {min_fit, sources, ...}}
GET    /api/apply/queue                     The review queue (grouped by state)
POST   /api/apply/{application_id}/fill      Run field-mapping agent (returns field_map + confidence)
POST   /api/apply/{application_id}/submit    Approve & submit a reviewed application
POST   /api/apply/batch-approve              Approve all high-confidence in queue
POST   /api/apply/{application_id}/skip      Remove from queue
GET    /api/autopilot                        Get autopilot config
PUT    /api/autopilot                        Update autopilot config (per-source toggles, thresholds)

# Profile + answer bank (fuel for the field-mapping agent)
GET    /api/profile/fields                   List profile fields
PUT    /api/profile/fields/{key}             Upsert a profile field (work auth, notice, salary)
GET    /api/answers                          List answer-bank entries
POST   /api/answers/{id}/approve             Approve a drafted answer for reuse
PUT    /api/answers/{id}                      Edit an answer

# Email status sync (v2)
GET    /api/email/accounts                   List connected inboxes (no tokens)
POST   /api/email/connect                    Begin OAuth (returns provider consent URL)
GET    /api/email/callback                   OAuth redirect → store encrypted token
DELETE /api/email/accounts/{id}              Disconnect + delete token immediately
POST   /api/email/{id}/sync                  Trigger an incremental sync now
GET    /api/status-events?state=proposed     Pending status transitions awaiting confirm
POST   /api/status-events/{id}/confirm       Apply a proposed transition
POST   /api/status-events/{id}/dismiss       Reject a proposed transition

POST   /api/eval/run                       Trigger eval suite
GET    /api/eval/runs/{id}
```

### 5.2 SSE Streaming

Long-running operations stream progress:
- `/api/scrape` — streams per-source progress
- `/api/generate` — streams generation tokens for UX
- `/api/eval/run` — streams per-case results
- `/api/apply/queue` — streams live state changes (queued → auto-filling → submitted / needs_review / blocked) so the Apply Queue updates in real time
- `/api/status-events/stream` *(v2)* — streams new email-derived status events so the Applications board moves cards and raises confirm prompts live

---

## 6. Frontend

> **Design-first.** The UI is specified before the backend because the frontend
> encapsulates what the user does. Design direction and clickable mockups live in
> [`docs/design/DIRECTION.md`](../design/DIRECTION.md) and
> [`docs/design/mockups/`](../design/mockups/) (static HTML + Tailwind, ported
> ~1:1 into Next.js). Direction in one line: *mission control for a job hunt* —
> dense, calm, scannable, with color reserved for one calibrated signal scale
> (match / confidence / groundedness: rose → amber → emerald).

### 6.1 Pages

| Route | Purpose | Mockup |
|---|---|---|
| `/` | Dashboard — pipeline + apply-queue health at a glance | `dashboard.html` |
| `/jobs` | Browse + search matched jobs (sorted by fit) | `jobs.html` |
| `/jobs/[id]` | Job detail: extraction, match, gaps, grounded generation | `job-detail.html` |
| `/apply` | **Apply Queue ★** — the auto-apply review surface; field-map cards, bulk approve, autopilot banner | `apply-queue.html` |
| `/applications` | Kanban-style post-submission pipeline; *(v2)* cards auto-advance from email, with a "confirm status" affordance on proposed transitions | `applications.html` |
| `/documents` | Generated résumés & cover letters, per-criteria scores, before/after vs uploaded baseline | `documents.html` |
| `/experience` | Manage experience corpus | `experience.html` |
| `/settings` | Sources + Autopilot toggles, Answer Bank, Profile fields; *(v2)* connect/disconnect inbox for status sync, with a "what we can see" read-only disclosure | `settings.html` |
| `/admin/prompts` | View prompt versions, diff between versions | `admin-prompts.html` |
| `/admin/calls` | LLM call inspector | `admin-calls.html` |
| `/admin/evals` | Eval suite runs and trends | `admin-evals.html` |

### 6.2 Key UX Flows

**Flow 1 — Bootstrap:**
1. User uploads existing resume PDF → LLM extracts experience items → user reviews/edits.
2. User triggers initial scrape with a natural language query.
3. User sees ranked job list with match scores.

**Flow 2 — Mass auto-apply (the core flow):**
1. User selects matched jobs (or "add top N by fit") → jobs enter the apply queue.
2. Apply Engine works each in the background: generates the tailored artifacts,
   field-maps the form, and either **auto-submits** (safe + high-confidence) or
   **queues for review**.
3. User opens the **Apply Queue** — *one* surface for every job board. The safe
   majority is already submitted; the rest appear as uniform field-map cards.
4. User skims the queue: confirms amber fields (unknown screening Qs, pinned
   work-authorization), then **bulk-approves high-confidence** or approves/edits
   per card. Blocked (CAPTCHA) items are flagged for manual handling.
5. Hundreds of applications cleared in minutes — the user never visited a single
   job board's UI.

**Flow 2b — Single deliberate apply:**
1. User opens a job → sees extraction, match, gaps, grounded resume preview.
2. Clicks "Add to apply queue" → handled by Flow 2, or edits/exports the PDF
   manually first.

**Flow 4 — Email status sync *(v2)*:**
1. In Settings, user connects their inbox via OAuth (read-only) and sees exactly
   what JobCraft can access.
2. A recruiter replies to a submitted application. The next sync ingests it,
   matches it to the application (domain/thread/ATS sender), and the classifier
   infers the new stage.
3. High-confidence forward moves apply automatically — the card slides to the next
   column on the Applications board in real time (SSE).
4. Low-confidence or high-stakes transitions (offer/rejected) surface as a
   "confirm status" prompt on the card with the quoted evidence line; one tap
   applies or dismisses.

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
| UI components | **shadcn/ui** (Radix primitives + Tailwind) | Copy-paste components that live *in our repo*, so the design tokens in `theme.js` / `components.css` stay the source of truth. We adopt the hard, accessibility-sensitive primitives (`Dialog`, `Select`, `DropdownMenu`, `Tabs`, `Tooltip`, `Checkbox`, `Toast`, `Table` headless bits) and keep our bespoke visual classes (`.chip`, `.badge`, `.skill-tag`, `.kanban-card`) layered on top. No heavy theme runtime to fight. |
| Icons | `lucide-react` | Ships with shadcn/ui; matches the stroke icons already used in the mockups |
| Email sync *(v2)* | Gmail API + Microsoft Graph; `google-api-python-client`, `msal` | Read-only inbox access for status tracking (§4.9) |
| Secret storage | OAuth tokens encrypted at rest (`cryptography` Fernet) or platform secret manager | Email refresh tokens are secrets — never plaintext |
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

### Phase 6 — Apply Engine (4 days)
- `profile_fields` + `answer_bank` tables; answer-bank embedding + similarity reuse
- `ApplyStrategy` adapters: LinkedIn Easy Apply, Greenhouse/Lever/Ashby form, MyCareersFuture, generic-form
- LLM field-mapping agent + per-field confidence
- Confidence gate + `AutopilotConfig`; `arq` apply workers with per-source rate limits
- Apply Queue UI (field-map review cards, bulk approve, autopilot banner) — port from `apply-queue.html`
- Hard safety rules: pinned knockout fields, no CAPTCHA solving, approved-answers-only
- **Demo:** Queue 50 SG jobs; watch the safe majority auto-submit and clear the rest from one review queue.

### Phase 7 — Pipeline + polish (2 days)
- Applications Kanban (post-submission stages)
- Admin/observability pages
- Cost dashboard
- README + architecture doc

### Phase 8 — Email status sync (3 days, v2)
- `email_accounts`, `email_messages`, `status_events` tables; token encryption
- Gmail + Outlook OAuth (read-only) connect/disconnect flow
- Incremental sync worker (`historyId` / Graph delta) + watch/poll fallback on `arq`
- Matcher (domain / thread / ATS-sender / LLM tie-break) → classifier (`LLMClient`, prompt-versioned)
- Confidence gate → auto-apply vs proposed `status_event`; SSE to the board
- `status_classification_v1` eval suite; Settings connect UI + board confirm affordance
- **Demo:** Connect inbox; a rejection email auto-moves a card after one-tap confirm.

**Total estimated effort:** ~21 working days with aggressive AI assistance. The
Apply Engine (browser automation + anti-bot) and Email Sync (OAuth + noisy
classification) are the riskiest phases and are deliberately sequenced last, after
the grounded-generation core is proven.

> **Phase 0 note:** scaffold the frontend by porting the static mockups in
> `docs/design/mockups/` into Next.js components, preserving the shared design
> tokens (`theme.js` → Tailwind config, `components.css` → `globals.css`). Pull in
> shadcn/ui primitives (`Dialog`, `Select`, `DropdownMenu`, `Tabs`, `Tooltip`,
> `Checkbox`, `Toast`) at this point and wire them to the existing token classes.

### 8.1 Task decomposition for model delegation

The phases above are sized for **Opus-as-orchestrator, Sonnet-as-implementer**.
The orchestrator owns architecture, interfaces, and review; bite-size tasks are
delegated to cheaper models. A task is delegation-ready when it is:

1. **Single-file or single-module** in scope, with the file path named.
2. **Interface-first** — the typed signature (Pydantic model / Protocol / API
   shape) is given by the orchestrator; the implementer fills the body only.
3. **Independently testable** — ships with the test command that proves it (TDD:
   the failing test is written or specified first).
4. **Context-bounded** — the implementer needs only the named interface + one
   pattern file to mirror, never the whole repo.

**Per-task hand-off template** (what the orchestrator passes to Sonnet):
```
TASK: <verb + single outcome, e.g. "Implement the Greenhouse JobSource adapter">
FILE: backend/scrapers/greenhouse.py
INTERFACE: implements JobSource (see §4.1) — list_jobs / fetch_job
MIRROR: backend/scrapers/lever.py  (same shape, already merged)
CONSTRAINTS: async httpx; respect rate limit; no new deps
DONE WHEN: `pytest tests/scrapers/test_greenhouse.py` green; ≥80% coverage
```

**Worked split — Phase 6 (Apply Engine) → delegatable tasks:**

| # | Task (→ Sonnet) | File | Done when |
|---|---|---|---|
| 6.1 | `profile_fields` + `answer_bank` tables + Alembic migration | `backend/db/migrations/` | migration applies; round-trip test green |
| 6.2 | Answer-bank embedding + similarity retrieval | `backend/apply/answer_bank.py` | top-k retrieval test green |
| 6.3 | `ApplyStrategy` Protocol + base form renderer | `backend/apply/base.py` | type-checks; mock form test |
| 6.4 | Greenhouse/Lever/Ashby form adapter | `backend/apply/ats_form.py` | fills fixture form; test green |
| 6.5 | MyCareersFuture adapter | `backend/apply/mycareersfuture.py` | fills fixture form; test green |
| 6.6 | LLM field-mapping agent + per-field confidence | `backend/apply/field_map.py` | maps fixture → field_map; eval case |
| 6.7 | Confidence gate + `AutopilotConfig` | `backend/apply/gate.py` | unit tests for each branch |
| 6.8 | `arq` apply worker + rate limits + `application_attempts` write | `backend/apply/worker.py` | integration test on mock strategy |
| 6.9 | Apply Queue UI port from `apply-queue.html` | `frontend/app/apply/` | renders; matches mockup |

Tasks 6.3–6.7 are pure logic (ideal for Sonnet); the orchestrator (Opus) owns the
interface contracts in 6.3, the safety-rule review, and integration in 6.8. The
same split applies to every phase — the worked example is the pattern to follow.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Scraping breaks when sites change | Multi-source design; each source independent; fallback to manual JD paste |
| LLM costs spiral | All calls logged with cost; daily budget alarm; cheap models (Haiku) for prefiltering |
| Resume generation hallucinates | Strict groundedness check; LLM-as-judge gate; UI flags ungrounded claims |
| Job sites detect/block scrapers | Tier-1 sources are official APIs (no scraping). LinkedIn/Glints are best-effort Tier-2 — low rate, expected to break, never a dependency. |
| **LinkedIn ToS / account restriction** | Scraping & automated apply violate LinkedIn ToS. Use a *dedicated disposable* session, low rate, daily cap. Architect for it to be banned/rotated; never block core flows on it. Personal single-user tool using the operator's own account. |
| **Auto-apply gets the account banned** | Per-source rate limits + `daily_cap`; pace submissions over time; prefer official ATS forms over scraped flows. |
| **CAPTCHA / bot-detection walls** | Hard stop — no solving services, no evasion. Blocked applications route to manual. |
| **Wrong answer to a knockout question** | Knockout fields (work auth, visa, eligibility, YOE) come only from the user's true `profile_fields`; never auto-guessed. Missing → queued, not invented. |
| **Mass applying lowers quality / annoys recruiters** | Every application is still tailored + grounded; a `min_fit` floor prevents applying to poor matches; volume comes from automation, not lowered standards. |
| **Email sync misclassifies a status** (e.g. marks active app rejected) | Forward-only auto-apply; offer/rejected always require one-tap confirm; every transition is a reversible `status_event` with the quoted evidence line; `status_classification_v1` eval guards regressions |
| **Email matched to wrong application** (same company, multiple roles) | Deterministic match first (thread/domain/ATS sender); LLM tie-break only on ambiguity; unmatched mail is dropped, not force-linked |
| **Inbox privacy / token leak** | Read-only OAuth scopes only; tokens encrypted at rest, never logged or returned; minimal retention (matched metadata + snippet); one-click disconnect deletes the token |
| **Gmail/Graph push subscription expiry** | `watch_expires_at` tracked and renewed by the sync worker; periodic poll is the always-on fallback so nothing is missed if push lapses |
| Spec is too large to finish in one sprint | Phased plan — each phase is independently useful; tasks decomposed for Sonnet delegation (§8.1) |
| Interview-related risk: "did AI write all this?" | The eval suite + observability + prompt versioning are deeply your engineering work and impossible to fake credibly. Lean on those in interviews. |

---

## 10. Out of Scope (v1)

**Now in scope** (promoted from the original out-of-scope list): auto-submission of
applications (§4.8), LinkedIn scraping (§4.1, best-effort Tier 2), and the
Singapore-focused multi-source scraper.

Still out of scope:

- Browser extension integrations
- Multi-user / multi-tenant accounts with auth (single-user, personal-use MVP)
- Applying on behalf of third parties (JobCraft applies only as its own operator)
- CAPTCHA-solving services or bot-detection evasion (deliberately excluded — see §9)
- Mobile UI (read-only triage only)
- Fine-tuning custom models
- Multi-language resumes
- Job recommendation based on past application outcomes (great v2 feature)

> **Moved into scope as v2 (Phase 8):** automatic application-status tracking from
> the user's email (§4.9). It is sequenced after the v1 core but fully specified
> here so the data model and Applications board are built v2-ready from day one.

---

## 11. What This Project Demonstrates for FDE Interviews

| Concept | Where It Shows Up |
|---|---|
| **RAG** | Experience corpus → resume generation; semantic job search |
| **Structured outputs** | Job extraction; match scoring; filter parsing |
| **LLM-as-judge** | Match scoring; groundedness check; eval rubrics |
| **Evals & regression testing** | Entire `eval/` subsystem |
| **Prompt engineering & versioning** | `prompt_versions` table; admin diff view |
| **Tool use / agentic workflows** | Scrape → extract → match → generate → **auto-apply** chain |
| **Agentic browser automation** | Apply Engine: LLM field-mapping agent fills real forms with a confidence gate and hard safety rules |
| **Noisy-source classification + OAuth integration** | Email Status Tracker (v2): match recruiter mail → application, LLM-classify → pipeline stage, confidence-gated with human confirm |
| **Observability for AI systems** | `llm_calls` table; admin dashboard |
| **Cost/quality tradeoffs** | Two-stage matcher; per-call cost tracking |
| **Production engineering** | Async, typed APIs, migrations, eval CI |
| **Customer-facing thinking** | The whole UX is built around a real user (you), with grounding/uncertainty surfaced honestly |

This is the project we want on the resume. It's not a chatbot wrapper. It's an end-to-end AI system with the same architectural concerns Anthropic and OpenAI think about every day for their enterprise deployments.
