# app/tests/test_tenant_middleware.py

import pytest


@pytest.mark.asyncio
async def test_valid_tenant_header(client):
    # /health has no auth guard — purely tests tenant middleware
    response = await client.get(
        "/health",
        headers={"X-Tenant-ID": "acme"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_tenant(client):
    # Invalid slug — tenant not found → 404
    response = await client.get(
        "/health",
        headers={"X-Tenant-ID": "invalid"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_missing_tenant(client):
    # No header at all → 400
    response = await client.get("/health")
    assert response.status_code == 400