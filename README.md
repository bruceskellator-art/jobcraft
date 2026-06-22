# JobCraft

> AI-powered job targeting and resume optimization system.

JobCraft scrapes job listings, deeply analyzes each one, scores your fit, identifies skill gaps, and generates tailored resumes and cover letters — all grounded in your actual experience, with full observability and evals.

**Status:** Specification phase. Implementation incoming.

## Why

Tailoring resumes for each application is painful and slow. Generic AI resume tools hallucinate experience and produce templated output. JobCraft is built around two principles:

1. **Strictly grounded generation.** Every claim in a generated resume traces back to a real experience item you've recorded. No invention.
2. **Production-grade AI engineering.** Evals, prompt versioning, observability, structured outputs, RAG, agentic workflows — the same concerns serious enterprise AI deployments care about.

## The Stack

Python + FastAPI on the backend, Next.js on the frontend, Postgres + Qdrant for storage, Anthropic + OpenAI APIs for LLMs. Everything async, everything typed, everything observable.

## The Spec

See [docs/specs/2026-06-22-jobcraft-design.md](docs/specs/2026-06-22-jobcraft-design.md) for the full design.

## Roadmap

Phased implementation over ~2-3 weeks:

- **Phase 0** — Project skeleton
- **Phase 1** — Experience corpus + LLM client abstraction
- **Phase 2** — Multi-source scraper + structured extraction
- **Phase 3** — Two-stage matcher (embeddings + LLM-as-judge)
- **Phase 4** — Grounded resume + cover letter generation
- **Phase 5** — Eval suite + prompt versioning
- **Phase 6** — Application pipeline + observability dashboard

## License

MIT
