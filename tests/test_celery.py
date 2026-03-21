# tests/test_celery.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
from datetime import datetime, timezone, timedelta
import secrets
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# These are already set by root conftest.py but set here too for safety
SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

from app.main import app
from app.models.tenant import Tenant
from app.models.user import User
from app.models.role import Role
from app.models.invitation import Invitation
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_EMAILS = ["celery_owner@test.com", "celery_member@test.com"]


def _make_engine():
    return create_async_engine(DATABASE_URL, echo=False)


async def _get_token(client, email, password="secret123"):
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


@pytest_asyncio.fixture
async def setup_celery_users():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        for role_name, email in [
            ("owner", "celery_owner@test.com"),
            ("member", "celery_member@test.com"),
        ]:
            role = (await db.execute(
                select(Role).where(
                    Role.tenant_id == tenant.id,
                    Role.name == role_name,
                )
            )).scalar_one()
            db.add(User(
                email=email,
                hashed_password=hash_password("secret123"),
                tenant_id=tenant.id,
                role=role_name,
                role_id=role.id,
            ))
        await db.commit()

    await engine.dispose()
    yield

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_celery_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Task execution tests (called directly, no worker needed) ──────

def test_clean_expired_invitations_task():
    """Run the task synchronously using localhost DB URL."""
    # Patch the URL inside the task module before calling
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL

    try:
        from app.worker.tasks import clean_expired_invitations
        result = clean_expired_invitations.apply().get()
        assert "expired_deleted" in result
        assert "accepted_deleted" in result
        assert "ran_at" in result
    finally:
        task_module.SYNC_DATABASE_URL = original


def test_collect_usage_stats_task():
    """Run the usage stats task synchronously."""
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL

    try:
        from app.worker.tasks import collect_usage_stats
        result = collect_usage_stats.apply().get()
        assert "tenants_processed" in result
        assert result["tenants_processed"] >= 0
    finally:
        task_module.SYNC_DATABASE_URL = original


def test_daily_digest_task():
    """Run the daily digest task synchronously."""
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL

    try:
        from app.worker.tasks import send_daily_digest
        result = send_daily_digest.apply().get()
        assert "digests_sent" in result
        assert "ran_at" in result
    finally:
        task_module.SYNC_DATABASE_URL = original


def test_clean_expired_invitations_removes_stale():
    """Insert a stale invitation and verify the task deletes it."""
    import psycopg2
    from urllib.parse import urlparse

    # Use localhost URL
    sync_url = SYNC_DATABASE_URL
    parsed = urlparse(sync_url.replace("postgresql://", "http://"))

    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    cur = conn.cursor()

    cur.execute("SELECT id FROM tenants WHERE slug = 'acme'")
    tenant_id = cur.fetchone()[0]

    cur.execute("SELECT id FROM roles WHERE tenant_id = %s LIMIT 1", (tenant_id,))
    role_id = cur.fetchone()[0]

    # Insert expired invitation (25h past expiry)
    stale_token = secrets.token_urlsafe(16)
    cur.execute("""
        INSERT INTO invitations (email, tenant_id, role_id, token, expires_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        "stale@test.com",
        tenant_id,
        role_id,
        stale_token,
        datetime.now(timezone.utc) - timedelta(hours=25),
    ))
    conn.commit()

    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL

    try:
        from app.worker.tasks import clean_expired_invitations
        result = clean_expired_invitations.apply().get()

        cur.execute("SELECT id FROM invitations WHERE token = %s", (stale_token,))
        assert cur.fetchone() is None, "Stale invitation should have been deleted"
        assert result["expired_deleted"] >= 1
    finally:
        task_module.SYNC_DATABASE_URL = original
        cur.close()
        conn.close()


# ── Task status API tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_status_polling(client):
    """Trigger a task and poll its status."""
    token = await _get_token(client, "celery_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    res = await client.post(
        "/tasks/trigger/collect_usage_stats",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert "task_id" in data
    assert data["status"] == "QUEUED"
    assert "poll_url" in data

    task_id = data["task_id"]

    res2 = await client.get(
        f"/tasks/{task_id}/status",
        headers=headers,
    )
    assert res2.status_code == 200
    status_data = res2.json()["data"]
    assert status_data["task_id"] == task_id
    assert status_data["status"] in ["PENDING", "STARTED", "SUCCESS", "FAILURE"]


@pytest.mark.asyncio
async def test_unknown_task_returns_400(client):
    token = await _get_token(client, "celery_owner@test.com")
    res = await client.post(
        "/tasks/trigger/nonexistent_task",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_usage_stats_endpoint(client):
    """After running collect_usage_stats, stats should be available."""
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL

    try:
        from app.worker.tasks import collect_usage_stats
        collect_usage_stats.apply().get()
    finally:
        task_module.SYNC_DATABASE_URL = original

    token = await _get_token(client, "celery_owner@test.com")
    res = await client.get(
        "/tasks/stats/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert "total_members" in data or "message" in data


@pytest.mark.asyncio
async def test_member_cannot_trigger_task(client):
    token = await _get_token(client, "celery_member@test.com")
    res = await client.post(
        "/tasks/trigger/collect_usage_stats",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403