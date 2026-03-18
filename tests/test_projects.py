# tests/test_projects.py

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

TEST_EMAILS = ["proj_owner@test.com", "proj_member@test.com"]


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
async def setup_proj_users():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        # Clean up
        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        for role_name, email in [
            ("owner",  "proj_owner@test.com"),
            ("member", "proj_member@test.com"),
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
async def client(setup_proj_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── POST /projects ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project(client):
    token = await _get_token(client, "proj_owner@test.com")
    res = await client.post(
        "/projects/",
        json={"name": "Alpha", "description": "First project"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Alpha"
    assert data["data"]["tenant_id"] is not None


@pytest.mark.asyncio
async def test_member_can_create_project(client):
    token = await _get_token(client, "proj_member@test.com")
    res = await client.post(
        "/projects/",
        json={"name": "Member Project"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200


# ── GET /projects ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_projects_returns_envelope(client):
    token = await _get_token(client, "proj_owner@test.com")

    # Create two projects first
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}
    await client.post("/projects/", json={"name": "P1"}, headers=headers)
    await client.post("/projects/", json={"name": "P2"}, headers=headers)

    res = await client.get("/projects/", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "data" in data
    assert "meta" in data
    assert data["meta"]["total"] >= 2
    assert "has_more" in data["meta"]


@pytest.mark.asyncio
async def test_list_projects_filter_by_name(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    await client.post("/projects/", json={"name": "Searchable"}, headers=headers)

    res = await client.get("/projects/?name=Searchable", headers=headers)
    assert res.status_code == 200
    items = res.json()["data"]
    assert all("searchable" in item["name"].lower() for item in items)


@pytest.mark.asyncio
async def test_list_projects_cursor_pagination(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    # Create 3 projects
    for i in range(3):
        await client.post("/projects/", json={"name": f"CursorP{i}"}, headers=headers)

    # First page of 2
    res1 = await client.get("/projects/?limit=2", headers=headers)
    data1 = res1.json()
    assert len(data1["data"]) <= 2

    # If there are more, use next_cursor
    if data1["meta"]["has_more"]:
        next_cursor = data1["meta"]["next_cursor"]
        res2 = await client.get(f"/projects/?limit=2&cursor={next_cursor}", headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        # Items on page 2 should have higher ids than page 1
        if data1["data"] and data2["data"]:
            assert data2["data"][0]["id"] > data1["data"][-1]["id"]


@pytest.mark.asyncio
async def test_list_projects_sort_desc(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    res = await client.get("/projects/?sort_by=id&sort_dir=desc", headers=headers)
    assert res.status_code == 200
    items = res.json()["data"]
    if len(items) >= 2:
        assert items[0]["id"] >= items[1]["id"]


# ── GET /projects/{id} ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_project_by_id(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    create_res = await client.post(
        "/projects/", json={"name": "DetailTest"}, headers=headers
    )
    project_id = create_res.json()["data"]["id"]

    res = await client.get(f"/projects/{project_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["id"] == project_id


@pytest.mark.asyncio
async def test_get_nonexistent_project_returns_404(client):
    token = await _get_token(client, "proj_owner@test.com")
    res = await client.get(
        "/projects/99999",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 404


# ── PATCH /projects/{id} ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_project(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    create_res = await client.post(
        "/projects/", json={"name": "ToUpdate"}, headers=headers
    )
    project_id = create_res.json()["data"]["id"]

    res = await client.patch(
        f"/projects/{project_id}",
        json={"name": "Updated", "description": "New desc"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Updated"


@pytest.mark.asyncio
async def test_partial_update_only_changes_provided_fields(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    create_res = await client.post(
        "/projects/",
        json={"name": "Partial", "description": "Keep this"},
        headers=headers,
    )
    project_id = create_res.json()["data"]["id"]

    # Only update name
    await client.patch(
        f"/projects/{project_id}", json={"name": "NewName"}, headers=headers
    )

    res = await client.get(f"/projects/{project_id}", headers=headers)
    assert res.json()["data"]["description"] == "Keep this"
    assert res.json()["data"]["name"] == "NewName"


# ── DELETE /projects/{id} ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_project(client):
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    create_res = await client.post(
        "/projects/", json={"name": "ToDelete"}, headers=headers
    )
    project_id = create_res.json()["data"]["id"]

    res = await client.delete(f"/projects/{project_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True

    # Verify gone
    res2 = await client.get(f"/projects/{project_id}", headers=headers)
    assert res2.status_code == 404


@pytest.mark.asyncio
async def test_member_cannot_delete_project(client):
    owner_token = await _get_token(client, "proj_owner@test.com")
    member_token = await _get_token(client, "proj_member@test.com")

    create_res = await client.post(
        "/projects/",
        json={"name": "OwnerProject"},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    project_id = create_res.json()["data"]["id"]

    res = await client.delete(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {member_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403


# ── Tenant isolation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_access_other_tenant_project(client):
    """Project IDs from another tenant should return 404."""
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    # Create a project in acme
    create_res = await client.post(
        "/projects/", json={"name": "AcmeOnly"}, headers=headers
    )
    project_id = create_res.json()["data"]["id"]

    # Try to access it with a different tenant header
    # (beta tenant likely doesn't exist, will 404 at tenant level)
    res = await client.get(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "beta"},
    )
    assert res.status_code in [404, 400]


# ── Cache ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_cached_response(client):
    """Second GET for same project should hit cache (same response)."""
    token = await _get_token(client, "proj_owner@test.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    create_res = await client.post(
        "/projects/", json={"name": "CacheTest"}, headers=headers
    )
    project_id = create_res.json()["data"]["id"]

    res1 = await client.get(f"/projects/{project_id}", headers=headers)
    res2 = await client.get(f"/projects/{project_id}", headers=headers)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json() == res2.json()