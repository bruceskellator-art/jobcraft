# JobCraft Backend

FastAPI backend for the JobCraft AI job-application tool.

## Quickstart

### 1. Create the virtual environment

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
```

### 2. Install the project (with dev dependencies)

```bash
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env as needed — all vars use the JOBCRAFT_ prefix
```

### 4. Run the development server

```bash
uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>.

- Health check: `GET /health`
- Root: `GET /`
- Interactive docs: `GET /docs`

## Running Tests

```bash
pytest
```

## Linting

```bash
ruff check .
```

## Type checking

```bash
mypy app
```

## Environment Variables

See `.env.example` for the full list of `JOBCRAFT_*` variables and their defaults.
