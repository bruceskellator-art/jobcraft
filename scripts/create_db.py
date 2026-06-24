#!/usr/bin/env python3
"""
Create the database schema from ORM models without running Alembic migrations.

Useful for the no-Docker dev setup (SQLite) where the Postgres-specific
migration files can't run. After this script, `alembic stamp head` marks
the DB as current so future `alembic upgrade head` calls are no-ops.

Usage (from backend/):
    python ../scripts/create_db.py
    alembic stamp head
"""
import asyncio
import sys

sys.path.insert(0, ".")

import app.db.models  # noqa: F401, E402 — registers all models on Base.metadata
from app.config import get_settings  # noqa: E402
from app.db.base import Base, make_engine  # noqa: E402


async def main() -> None:
    url = get_settings().database_url
    print(f"Creating schema on: {url}")
    engine = make_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Done. Run `alembic stamp head` next.")


asyncio.run(main())
