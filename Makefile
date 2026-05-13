.PHONY: up down dev-backend dev-frontend test-backend lint fmt

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

## Run backend tests
test-backend:
	pytest backend/tests -q

# ── Frontend ──────────────────────────────────────────────────────────────────

## Run the Next.js dev server
dev-frontend:
	cd frontend && pnpm dev

# ── Code quality ──────────────────────────────────────────────────────────────

## Lint backend (ruff) and frontend (eslint via pnpm lint)
lint:
	ruff check backend
	cd frontend && pnpm lint

## Auto-fix backend formatting (ruff format) and frontend (prettier via pnpm)
fmt:
	ruff format backend
	cd frontend && pnpm format 2>/dev/null || true
