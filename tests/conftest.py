import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()
os.environ["TESTING"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["EMAIL_ENABLED"] = "false"

from app.main import app
from app.models.tenant import Tenant

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest_asyncio.fixture
async def setup_tenant():
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            tenant = Tenant(name="Acme", slug="acme", plan="free")
            db.add(tenant)
            await db.flush()

            # Seed default roles and permissions for this tenant
            from app.services.seed_roles import seed_default_roles
            await seed_default_roles(db, tenant.id)
        else:
            # Ensure roles exist even if tenant was already there
            from app.services.seed_roles import seed_default_roles
            await seed_default_roles(db, tenant.id)

    await engine.dispose()


@pytest_asyncio.fixture
async def clean_users(setup_tenant):
    """Delete test users before and after each test."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        from app.models.user import User
        await db.execute(delete(User).where(User.email == "test@example.com"))
        await db.commit()

    await engine.dispose()

    yield

    engine2 = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal2 = async_sessionmaker(engine2, expire_on_commit=False)

    async with AsyncSessionLocal2() as db:
        from app.models.user import User
        await db.execute(delete(User).where(User.email == "test@example.com"))
        await db.commit()

    await engine2.dispose()


@pytest_asyncio.fixture
async def client(clean_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client