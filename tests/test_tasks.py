# tests/test_tasks.py

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
import asyncio, sys, os
from dotenv import load_dotenv

load_dotenv()

from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.project import Project
from app.models.task import Task
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")
TEST_EMAILS = ["task_owner@test.com", "task_member@test.com"]


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
async def setup_task_users():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        await db.execute(delete(Task).where(Task.tenant_id == tenant.id))
        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        for role_name, email in [("owner", "task_owner@test.com"), ("member", "task_member@test.com")]:
            role = (await db.execute(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == role_name)
            )).scalar_one()
            db.add(User(
                email=email, hashed_password=hash_password("secret123"),
                tenant_id=tenant.id, role=role_name, role_id=role.id,
            ))
        await db.commit()

    await engine.dispose()
    yield

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        await db.execute(delete(Task).where(Task.tenant_id == tenant.id))
        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_task_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_project(client, token):
    res = await client.post(
        "/projects/",
        json={"name": "Test Project"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    return res.json()["data"]["id"]


async def _create_task(client, token, project_id, title="Test Task"):
    res = await client.post(
        f"/projects/{project_id}/tasks/",
        json={"title": title, "status": "todo"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


@pytest.mark.asyncio
async def test_create_task(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)
    assert task_id is not None


@pytest.mark.asyncio
async def test_list_tasks(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    await _create_task(client, token, project_id, "T1")
    await _create_task(client, token, project_id, "T2")

    res = await client.get(
        f"/projects/{project_id}/tasks/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["meta"]["total"] >= 2


@pytest.mark.asyncio
async def test_get_task_by_id(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    res = await client.get(
        f"/projects/{project_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["id"] == task_id


@pytest.mark.asyncio
async def test_update_task_status(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    res = await client.patch(
        f"/projects/{project_id}/tasks/{task_id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_delete_task(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    res = await client.delete(
        f"/projects/{project_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_member_cannot_delete_task(client):
    owner_token = await _get_token(client, "task_owner@test.com")
    member_token = await _get_token(client, "task_member@test.com")

    project_id = await _create_project(client, owner_token)
    task_id = await _create_task(client, owner_token, project_id)

    res = await client.delete(
        f"/projects/{project_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {member_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_task_in_wrong_project_returns_404(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    task_id = await _create_task(client, token, project_id)

    res = await client.get(
        f"/projects/99999/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_filter_tasks_by_status(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}

    await _create_task(client, token, project_id, "TodoTask")
    task_id = await _create_task(client, token, project_id, "DoneTask")
    await client.patch(
        f"/projects/{project_id}/tasks/{task_id}",
        json={"status": "done"},
        headers=headers,
    )

    res = await client.get(
        f"/projects/{project_id}/tasks/?status=done",
        headers=headers,
    )
    assert res.status_code == 200
    items = res.json()["data"]
    assert all(t["status"] == "done" for t in items)


@pytest.mark.asyncio
async def test_audit_log_records_task_create(client):
    token = await _get_token(client, "task_owner@test.com")
    project_id = await _create_project(client, token)
    await _create_task(client, token, project_id, "AuditedTask")

    res = await client.get(
        "/audit-logs/?resource_type=task&action=create",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    logs = res.json()["data"]
    assert any(log["resource_type"] == "task" for log in logs)