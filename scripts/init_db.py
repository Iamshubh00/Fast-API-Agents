"""
Quick local setup: creates tables directly from the SQLAlchemy models.

This is fine for local dev/testing. For anything resembling production, replace this with
real Alembic migrations (alembic init, then `alembic revision --autogenerate`) so schema changes
are versioned and reviewable -- see the earlier discussion on migrations.

Run with: python -m scripts.init_db
"""

import asyncio

from app.db import engine
from app.models import Base


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")


if __name__ == "__main__":
    asyncio.run(main())
