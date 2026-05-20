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

## Pre-deploy security checklist

Items deferred from initial implementation — must be resolved before any multi-user or production deployment:

- [ ] Replace the `get_current_user` dev stub with real JWT/session auth (`app/deps.py`)
- [ ] Remove `user_id` from `ExperienceItemRead` response schema to prevent user enumeration (`app/schemas/experience.py`)
- [ ] Redact or truncate resume PII stored in `llm_calls.inputs` and `llm_calls.rendered_prompt` in production (`app/llm/client.py`)
- [ ] Remove the plaintext default credential from `database_url` field default (`app/config.py`)
- [ ] Validate that required API keys (e.g. `ANTHROPIC_API_KEY`) are present and non-empty at application startup (`app/main.py` or `app/config.py`)
