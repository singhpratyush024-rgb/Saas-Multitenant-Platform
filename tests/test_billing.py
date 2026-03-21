# tests/test_billing.py

import pytest
import pytest_asyncio
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
from datetime import datetime, timezone, timedelta
import asyncio
import sys
import os
from dotenv import load_dotenv
from unittest.mock import patch, MagicMock

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.plan import Plan
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_EMAILS = ["billing_owner@test.com"]


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


async def _seed_plans(db):
    from app.services.seed_plans import seed_plans
    await seed_plans(db)


@pytest_asyncio.fixture
async def setup_billing():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        await _seed_plans(db)

        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        # Clean slate
        tenant.plan = "free"
        tenant.stripe_customer_id = None
        tenant.stripe_subscription_id = None
        tenant.stripe_subscription_status = None
        tenant.trial_ends_at = None
        tenant.grace_period_ends_at = None

        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        role = (await db.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
        )).scalar_one()

        db.add(User(
            email="billing_owner@test.com",
            hashed_password=hash_password("secret123"),
            tenant_id=tenant.id,
            role="owner",
            role_id=role.id,
        ))
        await db.commit()

    await engine.dispose()
    yield

    # Teardown
    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant.plan = "free"
        tenant.stripe_customer_id = None
        tenant.stripe_subscription_id = None
        tenant.stripe_subscription_status = None
        tenant.trial_ends_at = None
        tenant.grace_period_ends_at = None
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_billing):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _owner_headers(token):
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": "acme"}


# ── GET /billing/plans ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_plans(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.get("/billing/plans", headers=_owner_headers(token))
    assert res.status_code == 200
    plans = res.json()["data"]
    assert len(plans) >= 4
    assert any(p["key"] == "free" for p in plans)
    assert any(p["key"] == "starter" for p in plans)


@pytest.mark.asyncio
async def test_current_plan_marked(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.get("/billing/plans", headers=_owner_headers(token))
    plans = res.json()["data"]
    assert len(plans) > 0, "Plans list is empty"
    free_plan = next((p for p in plans if p["key"] == "free"), None)
    assert free_plan is not None
    assert free_plan["current"] is True


# ── GET /billing/status ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_billing_status(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.get("/billing/status", headers=_owner_headers(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["plan"] == "free"
    assert "limits" in data
    assert data["trial"] is None
    assert data["grace_period"] is None


# ── GET /billing/usage ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_summary(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.get("/billing/usage", headers=_owner_headers(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "usage" in data
    assert "members" in data["usage"]
    assert "projects" in data["usage"]
    assert "features" in data
    assert data["usage"]["members"]["limit"] == 3   # free plan


# ── POST /billing/subscribe ───────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_creates_checkout_session(client):
    token = await _get_token(client, "billing_owner@test.com")

    mock_customer = MagicMock()
    mock_customer.id = "cus_test_123"
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_session.id = "cs_test_123"

    with patch("stripe.Customer.create", return_value=mock_customer), \
         patch("stripe.checkout.Session.create", return_value=mock_session):
        res = await client.post(
            "/billing/subscribe",
            json={"plan_key": "starter"},
            headers=_owner_headers(token),
        )

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["checkout_url"] == "https://checkout.stripe.com/test"
    assert data["plan"] == "starter"


@pytest.mark.asyncio
async def test_subscribe_with_trial(client):
    token = await _get_token(client, "billing_owner@test.com")

    mock_customer = MagicMock()
    mock_customer.id = "cus_trial_123"
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/trial"
    mock_session.id = "cs_trial_123"

    with patch("stripe.Customer.create", return_value=mock_customer), \
         patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
        res = await client.post(
            "/billing/subscribe",
            json={"plan_key": "starter", "trial": True},
            headers=_owner_headers(token),
        )

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["trial_days"] == 14
    # Verify trial_period_days was passed to Stripe
    call_kwargs = mock_create.call_args[1]
    assert "subscription_data" in call_kwargs
    assert call_kwargs["subscription_data"]["trial_period_days"] == 14


@pytest.mark.asyncio
async def test_subscribe_to_unknown_plan_returns_404(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.post(
        "/billing/subscribe",
        json={"plan_key": "nonexistent"},
        headers=_owner_headers(token),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_subscribe_to_free_plan_returns_403(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.post(
        "/billing/subscribe",
        json={"plan_key": "free"},
        headers=_owner_headers(token),
    )
    assert res.status_code == 403


# ── Webhook tests ─────────────────────────────────────────────────

async def _simulate_webhook(client, event_type, event_data):
    payload = json.dumps({"type": event_type, "data": {"object": event_data}}).encode()
    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = json.loads(payload)
        return await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )


@pytest.mark.asyncio
async def test_webhook_checkout_upgrades_plan(client):
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant.stripe_customer_id = "cus_wh_test"
        tenant_id = tenant.id
        await db.commit()
    await engine.dispose()

    mock_sub = {"status": "active", "trial_end": None}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        res = await _simulate_webhook(client, "checkout.session.completed", {
            "metadata": {"tenant_id": str(tenant_id), "plan_key": "starter"},
            "subscription": "sub_wh_test",
            "customer": "cus_wh_test",
        })
    assert res.status_code == 200

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        assert tenant.plan == "starter"
        assert tenant.stripe_subscription_status == "active"
    await engine2.dispose()


@pytest.mark.asyncio
async def test_webhook_trial_checkout(client):
    """Checkout completed with trial — status should be trialing."""
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant.stripe_customer_id = "cus_trial_wh"
        tenant_id = tenant.id
        await db.commit()
    await engine.dispose()

    trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
    mock_sub = {"status": "trialing", "trial_end": trial_end_ts}

    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        res = await _simulate_webhook(client, "checkout.session.completed", {
            "metadata": {"tenant_id": str(tenant_id), "plan_key": "pro"},
            "subscription": "sub_trial_wh",
            "customer": "cus_trial_wh",
        })
    assert res.status_code == 200

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        assert tenant.plan == "pro"
        assert tenant.stripe_subscription_status == "trialing"
        assert tenant.trial_ends_at is not None
    await engine2.dispose()


@pytest.mark.asyncio
async def test_webhook_payment_failed_starts_grace_period(client):
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant.plan = "pro"
        tenant.stripe_customer_id = "cus_fail_test"
        tenant.stripe_subscription_id = "sub_fail_test"
        tenant.stripe_subscription_status = "active"
        tenant_id = tenant.id
        await db.commit()
    await engine.dispose()

    with patch("app.worker.tasks.send_email_async.delay"):
        res = await _simulate_webhook(client, "invoice.payment_failed", {
            "customer": "cus_fail_test",
        })
    assert res.status_code == 200

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        assert tenant.stripe_subscription_status == "past_due"
        assert tenant.grace_period_ends_at is not None
        # Still on pro during grace period
        assert tenant.plan == "pro"
    await engine2.dispose()


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades(client):
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant.plan = "pro"
        tenant.stripe_customer_id = "cus_cancel_test"
        tenant.stripe_subscription_id = "sub_cancel_test"
        tenant.stripe_subscription_status = "active"
        tenant_id = tenant.id
        await db.commit()
    await engine.dispose()

    res = await _simulate_webhook(client, "customer.subscription.deleted", {
        "customer": "cus_cancel_test", "status": "canceled",
    })
    assert res.status_code == 200

    engine2 = _make_engine()
    factory2 = async_sessionmaker(engine2, expire_on_commit=False)
    async with factory2() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        assert tenant.plan == "free"
        assert tenant.stripe_subscription_status == "canceled"
    await engine2.dispose()


# ── Plan limits ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_limits_in_status(client):
    token = await _get_token(client, "billing_owner@test.com")
    res = await client.get("/billing/status", headers=_owner_headers(token))
    limits = res.json()["data"]["limits"]
    assert limits["max_members"] == 3
    assert limits["can_use_api"] is False


# ── Full E2E: subscribe → use feature → cancel → feature locked ───

@pytest.mark.asyncio
async def test_e2e_subscribe_use_cancel_lock(client):
    """
    Full billing lifecycle:
    1. Start on free plan — API access blocked
    2. Subscribe to pro (mocked) → API access unlocked
    3. Cancel subscription → webhook fires → downgrade to free
    4. API access blocked again
    """
    token = await _get_token(client, "billing_owner@test.com")
    headers = _owner_headers(token)

    # ── Step 1: On free plan — verify can_use_api is False ────────
    res = await client.get("/billing/usage", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["features"]["can_use_api"] is False

    # ── Step 2: Simulate pro subscription via webhook ─────────────
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == "acme"))).scalar_one()
        tenant_id = tenant.id
        tenant.stripe_customer_id = "cus_e2e_test"
    await engine.dispose()

    mock_sub = {"status": "active", "trial_end": None}
    with patch("stripe.Subscription.retrieve", return_value=mock_sub):
        await _simulate_webhook(client, "checkout.session.completed", {
            "metadata": {"tenant_id": str(tenant_id), "plan_key": "pro"},
            "subscription": "sub_e2e_test",
            "customer": "cus_e2e_test",
        })

    # ── Step 3: Now on pro — can_use_api should be True ──────────
    # Re-login to get fresh token (tenant plan updated)
    token2 = await _get_token(client, "billing_owner@test.com")
    res2 = await client.get("/billing/usage", headers=_owner_headers(token2))
    assert res2.json()["data"]["features"]["can_use_api"] is True
    assert res2.json()["data"]["usage"]["members"]["limit"] == 50   # pro limit

    # ── Step 4: Cancel → webhook fires → downgrade to free ────────
    await _simulate_webhook(client, "customer.subscription.deleted", {
        "customer": "cus_e2e_test", "status": "canceled",
    })

    token3 = await _get_token(client, "billing_owner@test.com")
    res3 = await client.get("/billing/usage", headers=_owner_headers(token3))
    assert res3.json()["data"]["features"]["can_use_api"] is False
    assert res3.json()["data"]["usage"]["members"]["limit"] == 3   # back to free


# ── Trial downgrade task ──────────────────────────────────────────

def test_auto_downgrade_expired_trials_task():
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")
    try:
        from app.worker.tasks import auto_downgrade_expired_trials
        result = auto_downgrade_expired_trials.apply().get()
        assert "downgraded" in result
    finally:
        task_module.SYNC_DATABASE_URL = original


def test_auto_downgrade_grace_periods_task():
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")
    try:
        from app.worker.tasks import auto_downgrade_expired_grace_periods
        result = auto_downgrade_expired_grace_periods.apply().get()
        assert "downgraded" in result
    finally:
        task_module.SYNC_DATABASE_URL = original