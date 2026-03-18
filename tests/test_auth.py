import pytest


@pytest.mark.asyncio
async def test_auth_flow(client):

    tenant_headers = {
        "X-Tenant-ID": "acme"
    }

    # --------------------
    # Register
    # --------------------
    register_data = {
        "email": "test@example.com",
        "password": "password123"
    }

    res = await client.post(
        "/auth/register",
        json=register_data,
        headers=tenant_headers
    )

    assert res.status_code == 200


    # --------------------
    # Login
    # --------------------
    res = await client.post(
        "/auth/login",
        json=register_data,
        headers=tenant_headers
    )

    assert res.status_code == 200

    data = res.json()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]


    # --------------------
    # Access protected route
    # --------------------
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tenant-ID": "acme"
    }

    res = await client.get("/projects/", headers=auth_headers)

    assert res.status_code == 200


    # --------------------
    # Refresh token         ← was missing X-Tenant-ID, would 400
    # --------------------
    res = await client.post(
        "/auth/refresh",
        params={"refresh_token": refresh_token},
        headers=tenant_headers                  # ← added
    )

    assert res.status_code == 200


    # --------------------
    # Logout
    # --------------------
    res = await client.post(
        "/auth/logout",
        headers=auth_headers
    )

    assert res.status_code == 200