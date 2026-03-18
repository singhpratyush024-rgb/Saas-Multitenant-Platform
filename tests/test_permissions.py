# tests/test_permissions.py
#
# Tests the permission and role guard system.
# Uses /projects/ CRUD endpoints (real resources) instead of
# the old demo routes /projects/admin, /projects/owner, /projects/billing.

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

from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.project import Project
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")
TEST_EMAILS = ["owner@test.com", "admin@test.com", "member@test.com"]


def _make_engine():
    return create_async_engine(DATABASE_URL, echo=False)


async def _get_token(client, email, password="secret123"):
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["access_token"]


@pytest_asyncio.fixture
async def setup_test_users():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        for role_name, email in [
            ("owner",  "owner@test.com"),
            ("admin",  "admin@test.com"),
            ("member", "member@test.com"),
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
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()
        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_test_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Helper: create a project and return its id ────────────────────

async def _create_project(client, token, name="Test Project"):
    res = await client.post(
        "/projects/",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200, f"Create failed: {res.text}"
    return res.json()["data"]["id"]


# ── GET /projects/ — requires projects:read ───────────────────────

@pytest.mark.asyncio
async def test_member_can_list_projects(client):
    token = await _get_token(client, "member@test.com")
    res = await client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_list_projects(client):
    token = await _get_token(client, "admin@test.com")
    res = await client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_owner_can_list_projects(client):
    token = await _get_token(client, "owner@test.com")
    res = await client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


# ── DELETE /projects/{id} — requires projects:delete ─────────────

@pytest.mark.asyncio
async def test_member_cannot_delete_project(client):
    owner_token = await _get_token(client, "owner@test.com")
    member_token = await _get_token(client, "member@test.com")

    project_id = await _create_project(client, owner_token, "MemberDeleteTest")

    res = await client.delete(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {member_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_admin_can_delete_project(client):
    owner_token = await _get_token(client, "owner@test.com")
    admin_token = await _get_token(client, "admin@test.com")

    project_id = await _create_project(client, owner_token, "AdminDeleteTest")

    res = await client.delete(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {admin_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_owner_can_delete_project(client):
    token = await _get_token(client, "owner@test.com")
    project_id = await _create_project(client, token, "OwnerDeleteTest")

    res = await client.delete(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


# ── Role-based access — /members/me shows role permissions ───────

@pytest.mark.asyncio
async def test_member_has_limited_permissions(client):
    token = await _get_token(client, "member@test.com")
    res = await client.get(
        "/members/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    perms = res.json()["permissions"]
    assert "projects:delete" not in perms
    assert "billing:manage" not in perms
    assert "projects:read" in perms


@pytest.mark.asyncio
async def test_admin_has_no_billing_manage(client):
    """Admin has billing:read but NOT billing:manage."""
    token = await _get_token(client, "admin@test.com")
    res = await client.get(
        "/members/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    perms = res.json()["permissions"]
    assert "billing:manage" not in perms
    assert "billing:read" in perms


@pytest.mark.asyncio
async def test_owner_has_all_permissions(client):
    token = await _get_token(client, "owner@test.com")
    res = await client.get(
        "/members/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    perms = res.json()["permissions"]
    assert "billing:manage" in perms
    assert "tenant:manage" in perms
    assert "roles:manage" in perms


# ── Unauthenticated ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unauthenticated_blocked(client):
    res = await client.get(
        "/projects/",
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 401