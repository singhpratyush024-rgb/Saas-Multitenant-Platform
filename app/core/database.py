# app/core/database.py

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TESTING = os.getenv("TESTING", "false").lower() == "true"

Base = declarative_base()

# Module-level engine used in production
_engine = create_async_engine(DATABASE_URL, echo=True)
_AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    if TESTING:
        # In tests: fresh engine per call so each test's event loop
        # gets its own connection — prevents asyncpg loop conflicts
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            yield session
        await engine.dispose()
    else:
        # Production: reuse the module-level engine and connection pool
        async with _AsyncSessionLocal() as session:
            yield session