# JobCraft

> AI-powered job targeting and resume optimization system.

JobCraft scrapes job listings (Singapore-focused), deeply analyzes each one, scores your fit, identifies skill gaps, generates tailored resumes and cover letters — all grounded in your actual experience — and **auto-applies at scale** through a single review queue, with full observability and evals.

**Status:** Specification phase. Implementation incoming.

## Why

Tailoring resumes for each application is painful and slow. Generic AI resume tools hallucinate experience and produce templated output. JobCraft is built around two principles:

1. **Strictly grounded generation.** Every claim in a generated resume traces back to a real experience item you've recorded. No invention.
2. **Production-grade AI engineering.** Evals, prompt versioning, observability, structured outputs, RAG, agentic workflows — the same concerns serious enterprise AI deployments care about.

## The Stack

Python + FastAPI on the backend, Next.js on the frontend, Postgres + Qdrant for storage, Anthropic + OpenAI APIs for LLMs. Everything async, everything typed, everything observable.

## Monorepo Layout

```
backend/    Python 3.12 + FastAPI — API server, LLM client, scraper, matcher, generator
frontend/   Next.js 15 + React 19 + Tailwind — web UI
eval/       YAML eval suites for AI component quality and regression testing (Phase 5+)
docs/       Design specs, mockups, and architecture notes
```

## Quickstart

**1. Start Postgres and Qdrant**

```bash
docker compose up -d
```

**2. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
# API available at http://localhost:8000
```

**3. Frontend**

```bash
cd frontend
pnpm install
pnpm dev
# UI available at http://localhost:3000
```

Copy `.env.example` to `.env` and fill in your API keys before starting the backend.

## The Spec

See [docs/specs/2026-06-22-jobcraft-design.md](docs/specs/2026-06-22-jobcraft-design.md) for the full design.

## Design

Frontend is designed first. See [docs/design/DIRECTION.md](docs/design/DIRECTION.md) for the
design direction and [docs/design/mockups/](docs/design/mockups/) for clickable HTML+Tailwind
mockups (open `dashboard.html`).

## Roadmap

Phased implementation over ~3 weeks:

- **Phase 0** — Project skeleton (port design mockups into Next.js)
- **Phase 1** — Experience corpus + LLM client abstraction
- **Phase 2** — SG-focused multi-source scraper + structured extraction
- **Phase 3** — Two-stage matcher (embeddings + LLM-as-judge)
- **Phase 4** — Grounded resume + cover letter generation
- **Phase 5** — Eval suite + prompt versioning
- **Phase 6** — Auto-apply engine (field-mapping agent + confidence gate + answer bank)
- **Phase 7** — Application pipeline + observability dashboard

## License

MIT
