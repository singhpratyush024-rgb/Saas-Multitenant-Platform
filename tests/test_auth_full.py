# tests/test_auth_full.py
#
# Comprehensive auth tests:
# register, login, refresh, logout, blacklist, cross-tenant isolation

import pytest
from sqlalchemy import select, delete
from app.models.user import User
from app.models.tenant import Tenant


# ── Registration ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(acme_client):
    res = await acme_client.post(
        "/auth/register",
        json={"email": "new_reg@acme.com", "password": "password123"},
    )
    assert res.status_code == 200
    assert res.json()["message"] == "User created successfully"


@pytest.mark.asyncio
async def test_register_success(acme_client, db, tenant):
    # Clean up in case previous run left this user behind
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(User).where(User.email == "new_reg@acme.com", User.tenant_id == tenant.id)
    )
    await db.commit()

    res = await acme_client.post(
        "/auth/register",
        json={"email": "new_reg@acme.com", "password": "password123"},
    )
    assert res.status_code == 200
    assert res.json()["message"] == "User created successfully"

@pytest.mark.asyncio
async def test_register_invalid_email(acme_client):
    res = await acme_client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert res.status_code == 422
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_register_missing_password(acme_client):
    res = await acme_client.post(
        "/auth/register",
        json={"email": "valid@acme.com"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_register_assigns_default_member_role(acme_client, db, tenant):
    email = "role_check@acme.com"
    res = await acme_client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert res.status_code == 200

    user = (await db.execute(
        select(User).where(User.email == email, User.tenant_id == tenant.id)
    )).scalar_one_or_none()
    assert user is not None
    assert user.role == "member"
    assert user.role_id is not None

    # cleanup
    await db.delete(user)
    await db.commit()


@pytest.mark.asyncio
async def test_register_without_tenant_header(http_client):
    res = await http_client.post(
        "/auth/register",
        json={"email": "no_tenant@acme.com", "password": "password123"},
    )
    assert res.status_code == 400
    assert "X-Tenant-ID" in res.json()["detail"]


# ── Login ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(acme_client, member_user):
    res = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "secret123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(acme_client, member_user):
    res = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "wrongpassword"},
    )
    assert res.status_code == 401
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_login_nonexistent_user(acme_client):
    res = await acme_client.post(
        "/auth/login",
        json={"email": "ghost@acme.com", "password": "password123"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_role_in_token(acme_client, owner_user):
    """JWT payload should contain the user's role."""
    import base64, json as jsonlib
    res = await acme_client.post(
        "/auth/login",
        json={"email": owner_user.email, "password": "secret123"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    # Decode payload (middle segment)
    payload_b64 = token.split(".")[1]
    # Add padding
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = jsonlib.loads(base64.b64decode(payload_b64))
    assert payload["role"] == "owner"
    assert "user_id" in payload
    assert "tenant_id" in payload


# ── Token refresh ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refresh_token_success(acme_client, member_user):
    login = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "secret123"},
    )
    refresh_token = login.json()["refresh_token"]

    res = await acme_client.post(
        "/auth/refresh",
        params={"refresh_token": refresh_token},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(acme_client):
    res = await acme_client.post(
        "/auth/refresh",
        params={"refresh_token": "completely.fake.token"},
    )
    assert res.status_code == 401
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_new_access_token_works(acme_client, member_user):
    """Refreshed token should grant access to protected routes."""
    login = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "secret123"},
    )
    refresh_token = login.json()["refresh_token"]

    refresh = await acme_client.post(
        "/auth/refresh",
        params={"refresh_token": refresh_token},
    )
    new_token = refresh.json()["access_token"]

    res = await acme_client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert res.status_code == 200


# ── Logout + token blacklist ──────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_success(acme_client, member_user):
    login = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "secret123"},
    )
    token = login.json()["access_token"]

    res = await acme_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert "logged out" in res.json()["message"].lower()


@pytest.mark.asyncio
async def test_blacklisted_token_rejected(acme_client, member_user):
    """Token used after logout should return 401."""
    login = await acme_client.post(
        "/auth/login",
        json={"email": member_user.email, "password": "secret123"},
    )
    token = login.json()["access_token"]

    # Logout
    await acme_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Try to use the blacklisted token
    res = await acme_client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401
    assert "revoked" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_token_returns_401(acme_client):
    res = await acme_client.get("/projects/")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_returns_401(acme_client):
    res = await acme_client.get(
        "/projects/",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert res.status_code == 401


# ── Cross-tenant isolation ────────────────────────────────────────
@pytest.mark.asyncio
async def test_cross_tenant_access_blocked(http_client, db, tenant, member_user):
    from conftest import make_token

    # Create a second tenant (upsert — safe on re-runs)
    result = await db.execute(select(Tenant).where(Tenant.slug == "beta-iso-test"))
    beta = result.scalar_one_or_none()
    if not beta:
        beta = Tenant(name="Beta Corp", slug="beta-iso-test", plan="free")
        db.add(beta)
        await db.commit()

    token = make_token(member_user)

    res = await http_client.get(
        "/projects/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "beta-iso-test",
        },
    )
    assert res.status_code in [401, 404]

    # cleanup
    await db.delete(beta)
    await db.commit()


@pytest.mark.asyncio
async def test_invalid_tenant_header_returns_404(http_client, member_token):
    res = await http_client.get(
        "/projects/",
        headers={
            "Authorization": f"Bearer {member_token}",
            "X-Tenant-ID": "does-not-exist",
        },
    )
    assert res.status_code == 404
    assert res.json()["success"] is False


@pytest.mark.asyncio
async def test_missing_tenant_header_returns_400(http_client, member_token):
    res = await http_client.get(
        "/projects/",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 400
    assert "X-Tenant-ID" in res.json()["detail"]