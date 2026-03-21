# tests/test_billing_e2e.py
#
# Full E2E billing flow:
# subscribe → use feature → cancel → feature locked
# trial → auto-downgrade → grace period → downgrade
#
# All Stripe API calls are mocked — no real network requests.

import pytest
import pytest_asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, delete
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")

from app.main import app
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.models.plan import Plan
from app.models.project import Project
from app.core.security import hash_password

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_EMAILS = ["e2e_owner@test.com", "e2e_member@test.com"]


# ── Helpers ───────────────────────────────────────────────────────

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


async def _set_tenant_state(db, tenant_id: int, **kwargs):
    """Directly update tenant fields for test setup."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one()
    for k, v in kwargs.items():
        setattr(tenant, k, v)
    await db.commit()
    return tenant


def _mock_stripe_customer(customer_id="cus_e2e_test"):
    m = MagicMock()
    m.id = customer_id
    return m


def _mock_checkout_session(session_id="cs_e2e_test", plan_key="pro"):
    m = MagicMock()
    m.url = f"https://checkout.stripe.com/{session_id}"
    m.id = session_id
    return m


def _mock_subscription(sub_id="sub_e2e_test", status="active", trial_end=None):
    m = MagicMock()
    m.id = sub_id
    m.__getitem__ = lambda self, key: {
        "id": sub_id,
        "status": status,
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
        "trial_end": trial_end,
        "items": {"data": [{"price": {"unit_amount": 9900, "currency": "usd", "recurring": {"interval": "month"}}}]},
    }[key]
    m.get = lambda key, default=None: {
        "trial_end": trial_end,
        "status": status,
        "cancel_at_period_end": False,
    }.get(key, default)
    return m


def _make_webhook_payload(event_type: str, data: dict) -> bytes:
    return json.dumps({"type": event_type, "data": {"object": data}}).encode()


# ── Fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def setup_e2e():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        # Seed plans
        from app.services.seed_plans import seed_plans
        await seed_plans(db)

        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == "acme")
        )).scalar_one()

        # Clean state
        await db.execute(delete(Project).where(Project.tenant_id == tenant.id))
        await db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
        await db.commit()

        await _set_tenant_state(
            db, tenant.id,
            plan="free",
            stripe_customer_id=None,
            stripe_subscription_id=None,
            stripe_subscription_status=None,
            trial_ends_at=None,
            grace_period_ends_at=None,
        )

        for role_name, email in [("owner", "e2e_owner@test.com"), ("member", "e2e_member@test.com")]:
            role = (await db.execute(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == role_name)
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
        await _set_tenant_state(
            db, tenant.id,
            plan="free",
            stripe_customer_id=None,
            stripe_subscription_id=None,
            stripe_subscription_status=None,
            trial_ends_at=None,
            grace_period_ends_at=None,
        )
    await engine2.dispose()


@pytest_asyncio.fixture
async def client(setup_e2e):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    engine = _make_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


# ══════════════════════════════════════════════════════════════════
# E2E Flow 1: Subscribe → Use Feature → Cancel → Feature Locked
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_e2e_subscribe_use_cancel_lock(client, db_session):
    """
    Full flow:
    1. Start on free plan — API access blocked
    2. Subscribe to pro → webhook fires → plan upgrades
    3. API access now allowed
    4. Cancel subscription → webhook fires → downgrade to free
    5. API access blocked again
    """
    owner_token = await _get_token(client, "e2e_owner@test.com")
    headers = {"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"}

    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.slug == "acme")
    )).scalar_one()
    tenant_id = tenant.id

    # ── Step 1: Verify free plan status ──────────────────────────
    res = await client.get("/billing/status", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["plan"] == "free"

    # ── Step 2: Subscribe to pro (mock Stripe) ───────────────────
    with patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
         patch("stripe.checkout.Session.create", return_value=_mock_checkout_session(plan_key="pro")):
        res = await client.post(
            "/billing/subscribe",
            json={"plan_key": "pro"},
            headers=headers,
        )
    assert res.status_code == 200
    assert res.json()["data"]["plan"] == "pro"

    # ── Step 3: Simulate webhook — checkout.session.completed ────
    payload = _make_webhook_payload("checkout.session.completed", {
        "metadata": {"tenant_id": str(tenant_id), "plan_key": "pro"},
        "subscription": "sub_e2e_pro",
        "customer": "cus_e2e_test",
    })

    with patch("stripe.Webhook.construct_event") as mock_event, \
         patch("stripe.Subscription.retrieve") as mock_sub:
        mock_event.return_value = json.loads(payload)
        mock_sub.return_value = {"status": "active", "trial_end": None}

        res = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )
    assert res.status_code == 200

    # ── Step 4: Verify pro plan active ───────────────────────────
    await db_session.refresh(tenant)
    assert tenant.plan == "pro"
    assert tenant.stripe_subscription_status == "active"

    res = await client.get("/billing/status", headers=headers)
    data = res.json()["data"]
    assert data["plan"] == "pro"
    assert data["limits"]["can_use_api"] is True

    # ── Step 5: Use pro feature — create project (within limits) ─
    res = await client.post(
        "/projects/",
        json={"name": "Pro Project"},
        headers=headers,
    )
    assert res.status_code == 200

    # ── Step 6: Cancel subscription ──────────────────────────────
    with patch("stripe.Subscription.modify") as mock_cancel:
        mock_cancel.return_value = MagicMock()
        res = await client.post("/billing/cancel", headers=headers)
    assert res.status_code == 200

    # ── Step 7: Webhook — subscription deleted → downgrade ───────
    payload = _make_webhook_payload("customer.subscription.deleted", {
        "customer": "cus_e2e_test",
        "status": "canceled",
    })

    with patch("stripe.Webhook.construct_event") as mock_event:
        mock_event.return_value = json.loads(payload)
        res = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )
    assert res.status_code == 200

    # ── Step 8: Verify back on free plan ─────────────────────────
    await db_session.refresh(tenant)
    assert tenant.plan == "free"
    assert tenant.stripe_subscription_status == "canceled"

    res = await client.get("/billing/status", headers=headers)
    data = res.json()["data"]
    assert data["plan"] == "free"
    assert data["limits"]["can_use_api"] is False


# ══════════════════════════════════════════════════════════════════
# E2E Flow 2: Trial → Auto-Downgrade
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_e2e_trial_auto_downgrade(client, db_session):
    """
    Trial flow:
    1. Subscribe with trial=True
    2. Webhook sets status=trialing + trial_ends_at
    3. Trial period expires
    4. Celery task auto-downgrades to free
    """
    owner_token = await _get_token(client, "e2e_owner@test.com")
    headers = {"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"}

    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.slug == "acme")
    )).scalar_one()
    tenant_id = tenant.id

    # ── Step 1: Subscribe with trial ─────────────────────────────
    with patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
         patch("stripe.checkout.Session.create", return_value=_mock_checkout_session()):
        res = await client.post(
            "/billing/subscribe",
            json={"plan_key": "starter", "trial": True},
            headers=headers,
        )
    assert res.status_code == 200
    assert res.json()["data"]["trial"] is True

    # ── Step 2: Webhook — checkout with trialing status ──────────
    trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
    payload = _make_webhook_payload("checkout.session.completed", {
        "metadata": {"tenant_id": str(tenant_id), "plan_key": "starter"},
        "subscription": "sub_e2e_trial",
        "customer": "cus_e2e_test",
    })

    with patch("stripe.Webhook.construct_event") as mock_event, \
         patch("stripe.Subscription.retrieve") as mock_sub:
        mock_event.return_value = json.loads(payload)
        mock_sub.return_value = {"status": "trialing", "trial_end": trial_end_ts}

        res = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )
    assert res.status_code == 200

    # ── Step 3: Verify trialing status ───────────────────────────
    await db_session.refresh(tenant)
    assert tenant.plan == "starter"
    assert tenant.stripe_subscription_status == "trialing"
    assert tenant.trial_ends_at is not None

    res = await client.get("/billing/status", headers=headers)
    data = res.json()["data"]
    assert data["trial_active"] is True
    assert data["trial_days_left"] >= 13

    # ── Step 4: Simulate trial expiry by setting trial_ends_at to past
    await _set_tenant_state(
        db_session, tenant_id,
        trial_ends_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    # ── Step 5: Run auto-downgrade Celery task synchronously ─────
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL
    try:
        from app.worker.tasks import auto_downgrade_expired_trials
        result = auto_downgrade_expired_trials.apply().get()
        assert result["downgraded"] >= 1
    finally:
        task_module.SYNC_DATABASE_URL = original

    # ── Step 6: Verify downgraded to free ────────────────────────
    await db_session.refresh(tenant)
    assert tenant.plan == "free"
    assert tenant.stripe_subscription_status == "canceled"
    assert tenant.trial_ends_at is None


# ══════════════════════════════════════════════════════════════════
# E2E Flow 3: Payment Failure → Grace Period → Downgrade
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_e2e_payment_failure_grace_downgrade(client, db_session):
    """
    Payment failure flow:
    1. Tenant is on pro plan (active)
    2. Payment fails → webhook sets past_due + grace period
    3. Grace period expires
    4. Celery task auto-downgrades to free
    """
    owner_token = await _get_token(client, "e2e_owner@test.com")
    headers = {"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"}

    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.slug == "acme")
    )).scalar_one()
    tenant_id = tenant.id

    # ── Step 1: Set tenant to pro plan manually ───────────────────
    await _set_tenant_state(
        db_session, tenant_id,
        plan="pro",
        stripe_customer_id="cus_grace_test",
        stripe_subscription_id="sub_grace_test",
        stripe_subscription_status="active",
    )

    # ── Step 2: Webhook — payment failed ─────────────────────────
    payload = _make_webhook_payload("invoice.payment_failed", {
        "customer": "cus_grace_test",
    })

    with patch("stripe.Webhook.construct_event") as mock_event, \
         patch("app.worker.tasks.send_payment_failed_notification.delay"):
        mock_event.return_value = json.loads(payload)
        res = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )
    assert res.status_code == 200

    # ── Step 3: Verify grace period active ───────────────────────
    await db_session.refresh(tenant)
    assert tenant.stripe_subscription_status == "past_due"
    assert tenant.grace_period_ends_at is not None
    assert tenant.plan == "pro"   # still on pro during grace

    res = await client.get("/billing/status", headers=headers)
    data = res.json()["data"]
    assert data["grace_active"] is True
    assert data["grace_days_left"] >= 6

    # ── Step 4: Simulate grace period expiry ─────────────────────
    await _set_tenant_state(
        db_session, tenant_id,
        grace_period_ends_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    # ── Step 5: Run grace period downgrade task ───────────────────
    import app.worker.tasks as task_module
    original = task_module.SYNC_DATABASE_URL
    task_module.SYNC_DATABASE_URL = SYNC_DATABASE_URL
    try:
        from app.worker.tasks import auto_downgrade_expired_grace_periods
        result = auto_downgrade_expired_grace_periods.apply().get()
        assert result["downgraded"] >= 1
    finally:
        task_module.SYNC_DATABASE_URL = original

    # ── Step 6: Verify downgraded to free ────────────────────────
    await db_session.refresh(tenant)
    assert tenant.plan == "free"
    assert tenant.stripe_subscription_status == "canceled"
    assert tenant.grace_period_ends_at is None


# ══════════════════════════════════════════════════════════════════
# E2E Flow 4: Trial Ending Notification
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_e2e_trial_will_end_notification(client, db_session):
    """
    Stripe sends trial_will_end 3 days before trial ends.
    Verify webhook triggers notification task.
    """
    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.slug == "acme")
    )).scalar_one()

    await _set_tenant_state(
        db_session, tenant.id,
        plan="starter",
        stripe_customer_id="cus_trial_end_test",
        stripe_subscription_status="trialing",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=3),
    )

    trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    payload = _make_webhook_payload("customer.subscription.trial_will_end", {
        "customer": "cus_trial_end_test",
        "trial_end": trial_end_ts,
    })

    with patch("stripe.Webhook.construct_event") as mock_event, \
         patch("app.worker.tasks.send_trial_ending_notification.delay") as mock_task:
        mock_event.return_value = json.loads(payload)
        res = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=1,v1=test", "Content-Type": "application/json"},
        )

    assert res.status_code == 200
    mock_task.assert_called_once()
    call_kwargs = mock_task.call_args[1]
    assert call_kwargs["tenant_id"] == tenant.id


# ══════════════════════════════════════════════════════════════════
# Unit: Portal and invoice endpoints
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_billing_portal_requires_customer(client, db_session):
    """Tenant without Stripe customer gets 403 on portal."""
    owner_token = await _get_token(client, "e2e_owner@test.com")
    res = await client.post(
        "/billing/portal",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_billing_portal_returns_url(client, db_session):
    """With a customer ID, portal returns a URL."""
    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.slug == "acme")
    )).scalar_one()
    await _set_tenant_state(db_session, tenant.id, stripe_customer_id="cus_portal_test")

    owner_token = await _get_token(client, "e2e_owner@test.com")

    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/session/test"

    with patch("stripe.billing_portal.Session.create", return_value=mock_portal):
        res = await client.post(
            "/billing/portal",
            headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
        )

    assert res.status_code == 200
    assert res.json()["data"]["portal_url"] == "https://billing.stripe.com/session/test"


@pytest.mark.asyncio
async def test_invoices_empty_without_customer(client):
    """Tenant without customer gets empty invoice list."""
    owner_token = await _get_token(client, "e2e_owner@test.com")
    res = await client.get(
        "/billing/invoices",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    assert res.json()["data"] == []


@pytest.mark.asyncio
async def test_usage_summary_returns_all_resources(client):
    """Usage endpoint returns members, projects, tasks, storage."""
    owner_token = await _get_token(client, "e2e_owner@test.com")
    res = await client.get(
        "/billing/usage",
        headers={"Authorization": f"Bearer {owner_token}", "X-Tenant-ID": "acme"},
    )
    assert res.status_code == 200
    usage = res.json()["data"]["usage"]
    assert "members" in usage
    assert "projects" in usage
    assert "tasks" in usage
    assert "storage_mb" in usage
    assert usage["members"]["limit"] == 3   # free plan limit