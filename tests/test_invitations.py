# tests/test_invitations.py

import os
os.environ["EMAIL_ENABLED"] = "false"   # disable real email sending in tests

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
from datetime import datetime, timezone, timedelta
import secrets as secrets_mod
import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()

from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.invitation import Invitation
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DATABASE_URL = os.getenv("DATABASE_URL")

TEST_EMAILS = ["inv_owner@test.com", "inv_member@test.com"]
INVITE_EMAIL = "newmember@acme.com"


# ── Helpers ───────────────────────────────────────────────────────

def _make_engine():
    return create_async_engine(DATABASE_URL, echo=False)


async def _get_token(client, email, password):
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]


async def _get_member_role_id() -> int:
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()
        role = (await db.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.name == "member")
        )).scalar_one()
        role_id = role.id
    await engine.dispose()
    return role_id


async def _create_invite_in_db(*, email: str, expired: bool = False) -> str:
    """Insert an invitation directly into DB. Returns the raw token."""
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()
        role_id = await _get_member_role_id()
        now = datetime.now(timezone.utc)
        inv = Invitation(
            email=email,
            tenant_id=tenant.id,
            role_id=role_id,
            token=secrets_mod.token_urlsafe(32),
            expires_at=now - timedelta(hours=1) if expired else now + timedelta(hours=48),
        )
        db.add(inv)
        await db.commit()
        await db.refresh(inv)
        token = inv.token
    await engine.dispose()
    return token


# ── Fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def setup_users():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        # Clean up previous test data
        await db.execute(
            delete(Invitation).where(Invitation.tenant_id == tenant.id)
        )
        await db.execute(
            delete(User).where(User.email.in_(TEST_EMAILS + [INVITE_EMAIL]))
        )
        await db.commit()

        for role_name, email in [
            ("owner", "inv_owner@test.com"),
            ("member", "inv_member@test.com"),
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

    # Teardown
    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()
        await db.execute(
            delete(Invitation).where(Invitation.tenant_id == tenant.id)
        )
        await db.execute(
            delete(User).where(
                User.email.in_(TEST_EMAILS + [INVITE_EMAIL, "expired@acme.com"])
            )
        )
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── POST /invitations — create ────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_can_create_invitation(client):
    token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    res = await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == INVITE_EMAIL
    assert data["accepted_at"] is None


@pytest.mark.asyncio
async def test_member_cannot_create_invitation(client):
    token = await _get_token(client, "inv_member@test.com", "secret123")
    role_id = await _get_member_role_id()

    res = await client.post(
        "/invitations/",
        json={"email": "another@acme.com", "role_id": role_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_cannot_invite_existing_user(client):
    token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    res = await client.post(
        "/invitations/",
        json={"email": "inv_member@test.com", "role_id": role_id},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 400
    assert "already a member" in res.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_invite_invalid_role(client):
    token = await _get_token(client, "inv_owner@test.com", "secret123")

    res = await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": 99999},
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cannot_create_duplicate_pending_invitation(client):
    token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}
    payload = {"email": INVITE_EMAIL, "role_id": role_id}

    res1 = await client.post("/invitations/", json=payload, headers=headers)
    assert res1.status_code == 200

    res2 = await client.post("/invitations/", json=payload, headers=headers)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


# ── POST /invitations/accept ──────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_token_creates_user(client):
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )

    # Fetch token from DB
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        inv = (await db.execute(
            select(Invitation).where(Invitation.email == INVITE_EMAIL)
        )).scalar_one()
        raw_token = inv.token
    await engine.dispose()

    res = await client.post(
        "/invitations/accept",
        json={"token": raw_token, "password": "newpassword123"},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert "Account created" in res.json()["message"]


@pytest.mark.asyncio
async def test_invalid_token_returns_404(client):
    res = await client.post(
        "/invitations/accept",
        json={"token": "completelyfaketoken", "password": "password123"},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_returns_410(client):
    raw_token = await _create_invite_in_db(email="expired@acme.com", expired=True)

    res = await client.post(
        "/invitations/accept",
        json={"token": raw_token, "password": "password123"},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 410


@pytest.mark.asyncio
async def test_already_accepted_token_returns_409(client):
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )

    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        inv = (await db.execute(
            select(Invitation).where(Invitation.email == INVITE_EMAIL)
        )).scalar_one()
        raw_token = inv.token
    await engine.dispose()

    await client.post(
        "/invitations/accept",
        json={"token": raw_token, "password": "newpassword123"},
        headers={"X-Tenant-ID": "acme"},
    )

    res = await client.post(
        "/invitations/accept",
        json={"token": raw_token, "password": "newpassword123"},
        headers={"X-Tenant-ID": "acme"},
    )
    assert res.status_code == 409
    assert "already been accepted" in res.json()["detail"]


# ── POST /invitations/{id}/resend ─────────────────────────────────

@pytest.mark.asyncio
async def test_owner_can_resend_invitation(client):
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    # Create invite
    res = await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    invite_id = res.json()["id"]

    # Clear the Redis rate limit key so resend is allowed
    from app.core.redis import redis_client
    await redis_client.delete(f"resend_invite:{invite_id}")

    res2 = await client.post(
        f"/invitations/{invite_id}/resend",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res2.status_code == 200


@pytest.mark.asyncio
async def test_resend_rate_limited(client):
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    res = await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    invite_id = res.json()["id"]

    headers = {"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"}

    # Clear rate limit then do first resend
    from app.core.redis import redis_client
    await redis_client.delete(f"resend_invite:{invite_id}")
    await client.post(f"/invitations/{invite_id}/resend", headers=headers)

    # Second resend immediately — should be rate limited
    res2 = await client.post(f"/invitations/{invite_id}/resend", headers=headers)
    assert res2.status_code == 429
    assert "wait" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_resend_accepted_invitation(client):
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")
    role_id = await _get_member_role_id()

    res = await client.post(
        "/invitations/",
        json={"email": INVITE_EMAIL, "role_id": role_id},
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    invite_id = res.json()["id"]

    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        inv = (await db.execute(
            select(Invitation).where(Invitation.id == invite_id)
        )).scalar_one()
        raw_token = inv.token
    await engine.dispose()

    # Accept it
    await client.post(
        "/invitations/accept",
        json={"token": raw_token, "password": "newpassword123"},
        headers={"X-Tenant-ID": "acme"},
    )

    # Try resend
    res2 = await client.post(
        f"/invitations/{invite_id}/resend",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_resend_refreshes_expired_token(client):
    """Resending an expired invite generates a new token and extends expiry."""
    owner_token = await _get_token(client, "inv_owner@test.com", "secret123")

    raw_token = await _create_invite_in_db(email=INVITE_EMAIL, expired=True)

    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        inv = (await db.execute(
            select(Invitation).where(Invitation.email == INVITE_EMAIL)
        )).scalar_one()
        invite_id = inv.id
        old_token = inv.token
    await engine.dispose()

    from app.core.redis import redis_client
    await redis_client.delete(f"resend_invite:{invite_id}")

    res = await client.post(
        f"/invitations/{invite_id}/resend",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200

    # Verify token was refreshed in DB
    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        inv = (await db.execute(
            select(Invitation).where(Invitation.id == invite_id)
        )).scalar_one()
        assert inv.token != old_token
        assert inv.expires_at > datetime.now(timezone.utc)
    await engine2.dispose()


# ── GET /invitations ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_can_list_invitations(client):
    token = await _get_token(client, "inv_owner@test.com", "secret123")
    res = await client.get(
        "/invitations/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_member_cannot_list_invitations(client):
    token = await _get_token(client, "inv_member@test.com", "secret123")
    res = await client.get(
        "/invitations/",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403