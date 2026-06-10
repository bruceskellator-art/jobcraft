.PHONY: up down dev-backend dev-frontend test-backend typecheck lint fmt

# ── Docker Compose ────────────────────────────────────────────────────────────

## Start Postgres and Qdrant in the background
up:
	docker compose up -d

## Stop and remove containers
down:
	docker compose down

# ── Backend ───────────────────────────────────────────────────────────────────

## Run the FastAPI dev server (requires backend venv activated)
dev-backend:
	cd backend && uvicorn app.main:app --reload

## Run backend tests (from backend/ so pyproject config is discovered)
test-backend:
	cd backend && pytest tests -q

## Type-check backend (must run from backend/ for mypy config)
typecheck:
	cd backend && mypy app

# ── Frontend ──────────────────────────────────────────────────────────────────

## Run the Next.js dev server
dev-frontend:
	cd frontend && pnpm dev

# ── Code quality ──────────────────────────────────────────────────────────────

## Lint backend (ruff) and frontend (eslint via pnpm lint)
lint:
	cd backend && ruff check .
	cd frontend && pnpm lint

## Auto-fix backend formatting (ruff format) and frontend (prettier via pnpm)
fmt:
	cd backend && ruff format .
	cd frontend && pnpm format 2>/dev/null || true
