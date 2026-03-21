# conftest.py  (project root — sits next to pytest.ini)
#
# Global fixtures shared across ALL test files.
# Provides: db, tenant, roles, users of each role, auth tokens, http client.

import os
import asyncio
import sys

# ── Must be set before any app imports ───────────────────────────
os.environ["TESTING"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:Pratyushcr7@localhost:5432/saas_db"
os.environ["SYNC_DATABASE_URL"] = "postgresql://postgres:Pratyushcr7@localhost:5432/saas_db"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete

from app.main import app
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.core.security import hash_password, create_access_token

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.environ["DATABASE_URL"]

# ── Low-level helpers ─────────────────────────────────────────────────────────

def make_engine():
    return create_async_engine(DATABASE_URL, echo=False)


def make_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


# ── Core DB fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    """
    Fresh async DB session per test.
    Disposes engine after test to avoid loop conflicts.
    """
    engine = make_engine()
    factory = make_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


# ── Tenant fixture ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant(db) -> Tenant:
    """
    Ensures the 'acme' tenant exists with all roles and permissions seeded.
    Returns the Tenant ORM object.
    """
    result = await db.execute(select(Tenant).where(Tenant.slug == "acme"))
    t = result.scalar_one_or_none()

    if not t:
        t = Tenant(name="Acme Corp", slug="acme", plan="free")
        db.add(t)
        await db.flush()

    from app.services.seed_roles import seed_default_roles
    await seed_default_roles(db, t.id)

    return t


# ── Role fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def owner_role(db, tenant) -> Role:
    result = await db.execute(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def admin_role(db, tenant) -> Role:
    result = await db.execute(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == "admin")
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def member_role(db, tenant) -> Role:
    result = await db.execute(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == "member")
    )
    return result.scalar_one()


# ── User factory ──────────────────────────────────────────────────────────────

async def _create_user(db, tenant, role: Role, email: str, password: str = "secret123") -> User:
    """Create a user in the DB or return existing one."""
    result = await db.execute(
        select(User).where(User.email == email, User.tenant_id == tenant.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()

    user = User(
        email=email,
        hashed_password=hash_password(password),
        tenant_id=tenant.id,
        role=role.name,
        role_id=role.id,
    )
    db.add(user)
    await db.flush()
    return user


# ── User fixtures (one per role) ──────────────────────────────────────────────

@pytest_asyncio.fixture
async def owner_user(db, tenant, owner_role) -> User:
    user = await _create_user(db, tenant, owner_role, "fixture_owner@acme.com")
    await db.commit()
    yield user
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


@pytest_asyncio.fixture
async def admin_user(db, tenant, admin_role) -> User:
    user = await _create_user(db, tenant, admin_role, "fixture_admin@acme.com")
    await db.commit()
    yield user
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


@pytest_asyncio.fixture
async def member_user(db, tenant, member_role) -> User:
    user = await _create_user(db, tenant, member_role, "fixture_member@acme.com")
    await db.commit()
    yield user
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()


# ── Token factory ─────────────────────────────────────────────────────────────

def make_token(user: User) -> str:
    """Generate a JWT access token for a user (no DB/Redis call)."""
    return create_access_token({
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "role": user.role,
    })


@pytest_asyncio.fixture
async def owner_token(owner_user) -> str:
    return make_token(owner_user)


@pytest_asyncio.fixture
async def admin_token(admin_user) -> str:
    return make_token(admin_user)


@pytest_asyncio.fixture
async def member_token(member_user) -> str:
    return make_token(member_user)


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def http_client() -> AsyncClient:
    """Bare async HTTP client — no tenant header, no auth."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def acme_client(http_client) -> AsyncClient:
    """HTTP client with X-Tenant-ID: acme pre-set."""
    http_client.headers["X-Tenant-ID"] = "acme"
    yield http_client


# ── Authenticated client helpers ──────────────────────────────────────────────

@pytest_asyncio.fixture
async def owner_client(tenant, owner_token) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-Tenant-ID": tenant.slug,
            "Authorization": f"Bearer {owner_token}",
        },
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admin_client(tenant, admin_token) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-Tenant-ID": tenant.slug,
            "Authorization": f"Bearer {admin_token}",
        },
    ) as c:
        yield c


@pytest_asyncio.fixture
async def member_client(tenant, member_token) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={
            "X-Tenant-ID": tenant.slug,
            "Authorization": f"Bearer {member_token}",
        },
    ) as c:
        yield c


# ── Legacy fixtures (kept for backward compat with existing tests) ────────────

@pytest_asyncio.fixture
async def setup_tenant(tenant):
    """Alias for backward compatibility."""
    pass


@pytest_asyncio.fixture
async def clean_users(setup_tenant):
    engine = make_engine()
    factory = make_factory(engine)
    async with factory() as db:
        await db.execute(delete(User).where(User.email == "test@example.com"))
        await db.commit()
    await engine.dispose()
    yield
    engine2 = make_engine()
    factory2 = make_factory(engine2)
    async with factory2() as db:
        await db.execute(delete(User).where(User.email == "test@example.com"))
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(clean_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c