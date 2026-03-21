# app/api/routes/billing.py

import stripe
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import ForbiddenException, NotFoundException
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import owner_only, admin_or_owner
from app.models.tenant import Tenant
from app.models.plan import Plan
from app.models.user import User
from app.schemas.response import single

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

TRIAL_DAYS = 14
GRACE_PERIOD_DAYS = 7

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Schemas ───────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan_key: str
    trial: bool = False   # start with a trial period


# ── Helpers ───────────────────────────────────────────────────────

async def _get_plan(db: AsyncSession, key: str) -> Plan:
    result = await db.execute(
        select(Plan).where(Plan.key == key, Plan.is_active == True)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise NotFoundException(resource="Plan")
    return plan


async def _get_or_create_stripe_customer(
    tenant: Tenant, current_user: User, db: AsyncSession
) -> str:
    if not tenant.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            name=tenant.name,
            metadata={"tenant_id": str(tenant.id), "tenant_slug": tenant.slug},
        )
        tenant.stripe_customer_id = customer.id
        await db.commit()
    return tenant.stripe_customer_id


# ── GET /billing/plans ────────────────────────────────────────────

@router.get("/plans")
async def list_plans(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.price_usd_cents)
    )
    plans = result.scalars().all()
    return single([
        {
            "key": p.key,
            "name": p.name,
            "price_usd_cents": p.price_usd_cents,
            "price_display": f"${p.price_usd_cents // 100}/mo" if p.price_usd_cents else "Free",
            "limits": p.limits,
            "current": p.key == tenant.plan,
            "trial_available": p.key != "free",
        }
        for p in plans
    ])


# ── GET /billing/status ───────────────────────────────────────────

@router.get("/status")
async def billing_status(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan_result = await db.execute(select(Plan).where(Plan.key == tenant.plan))
    plan = plan_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    # Compute trial/grace status
    trial_active = (
        tenant.stripe_subscription_status == "trialing"
        and tenant.trial_ends_at
        and tenant.trial_ends_at > now
    )
    trial_days_left = None
    if trial_active and tenant.trial_ends_at:
        trial_days_left = (tenant.trial_ends_at - now).days

    grace_active = (
        tenant.stripe_subscription_status == "past_due"
        and tenant.grace_period_ends_at
        and tenant.grace_period_ends_at > now
    )
    grace_days_left = None
    if grace_active and tenant.grace_period_ends_at:
        grace_days_left = (tenant.grace_period_ends_at - now).days

    return single({
        "tenant_id": tenant.id,
        "plan": tenant.plan,
        "plan_name": plan.name if plan else tenant.plan.title(),
        "limits": plan.limits if plan else {},
        "stripe_customer_id": tenant.stripe_customer_id,
        "stripe_subscription_id": tenant.stripe_subscription_id,
        "stripe_subscription_status": tenant.stripe_subscription_status,
        "trial_active": trial_active,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "trial_days_left": trial_days_left,
        "trial": {
            "active": trial_active,
            "ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
            "days_left": trial_days_left,
        } if trial_active else None,
        "grace_active": grace_active,
        "grace_period_ends_at": tenant.grace_period_ends_at.isoformat() if tenant.grace_period_ends_at else None,
        "grace_days_left": grace_days_left,
        "grace_period": {
            "active": grace_active,
            "ends_at": tenant.grace_period_ends_at.isoformat() if tenant.grace_period_ends_at else None,
            "days_left": grace_days_left,
        } if grace_active else None,
    })


# ── GET /billing/subscription ─────────────────────────────────────

@router.get("/subscription")
async def get_subscription(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(owner_only()),
):
    if not tenant.stripe_subscription_id:
        return single({"message": "No active subscription", "plan": tenant.plan})

    try:
        sub = stripe.Subscription.retrieve(
            tenant.stripe_subscription_id,
            expand=["latest_invoice", "default_payment_method"],
        )
        item = sub["items"]["data"][0] if sub["items"]["data"] else {}
        price = item.get("price", {})

        return single({
            "subscription_id": sub["id"],
            "status": sub["status"],
            "plan": tenant.plan,
            "current_period_start": datetime.fromtimestamp(
                sub["current_period_start"], tz=timezone.utc
            ).isoformat(),
            "current_period_end": datetime.fromtimestamp(
                sub["current_period_end"], tz=timezone.utc
            ).isoformat(),
            "cancel_at_period_end": sub["cancel_at_period_end"],
            "trial_end": datetime.fromtimestamp(
                sub["trial_end"], tz=timezone.utc
            ).isoformat() if sub.get("trial_end") else None,
            "amount": price.get("unit_amount"),
            "currency": price.get("currency"),
            "interval": price.get("recurring", {}).get("interval"),
        })
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


# ── GET /billing/invoices ─────────────────────────────────────────

@router.get("/invoices")
async def list_invoices(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(admin_or_owner()),
    limit: int = 10,
):
    if not tenant.stripe_customer_id:
        return single([])

    try:
        invoices = stripe.Invoice.list(
            customer=tenant.stripe_customer_id,
            limit=limit,
        )
        return single([
            {
                "id": inv["id"],
                "number": inv.get("number"),
                "status": inv["status"],
                "amount_due": inv["amount_due"],
                "amount_paid": inv["amount_paid"],
                "currency": inv["currency"],
                "created": datetime.fromtimestamp(
                    inv["created"], tz=timezone.utc
                ).isoformat(),
                "invoice_pdf": inv.get("invoice_pdf"),
                "hosted_invoice_url": inv.get("hosted_invoice_url"),
            }
            for inv in invoices["data"]
        ])
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


# ── GET /billing/usage ────────────────────────────────────────────

@router.get("/usage")
async def usage_summary(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    from app.models.user import User as UserModel
    from app.models.project import Project
    from app.models.task import Task
    from app.models.file_upload import FileUpload

    plan_result = await db.execute(select(Plan).where(Plan.key == tenant.plan))
    plan = plan_result.scalar_one_or_none()
    limits = plan.limits if plan else {}

    # Current usage counts
    members = (await db.execute(
        select(func.count(UserModel.id)).where(UserModel.tenant_id == tenant.id)
    )).scalar()

    projects = (await db.execute(
        select(func.count(Project.id)).where(Project.tenant_id == tenant.id)
    )).scalar()

    tasks = (await db.execute(
        select(func.count(Task.id)).where(Task.tenant_id == tenant.id)
    )).scalar()

    storage_bytes = (await db.execute(
        select(func.coalesce(func.sum(FileUpload.size_bytes), 0))
        .where(FileUpload.tenant_id == tenant.id)
    )).scalar()

    storage_mb = round(storage_bytes / (1024 * 1024), 2)

    def _pct(used, limit):
        if limit == -1:
            return None   # unlimited
        if limit == 0:
            return 100
        return round((used / limit) * 100, 1)

    return single({
        "plan": tenant.plan,
        "usage": {
            "members": {
                "used": members,
                "limit": limits.get("max_members", 0),
                "percent": _pct(members, limits.get("max_members", 0)),
            },
            "projects": {
                "used": projects,
                "limit": limits.get("max_projects", 0),
                "percent": _pct(projects, limits.get("max_projects", 0)),
            },
            "tasks": {
                "used": tasks,
                "limit": None,
                "percent": None,
            },
            "storage_mb": {
                "used": storage_mb,
                "limit": limits.get("max_storage_mb", 0),
                "percent": _pct(storage_mb, limits.get("max_storage_mb", 0)),
            },
        },
        "features": {
            "can_use_api": limits.get("can_use_api", False),
            "max_members": limits.get("max_members", 0),
            "max_projects": limits.get("max_projects", 0),
            "max_storage_mb": limits.get("max_storage_mb", 0),
        },
    })


# ── POST /billing/subscribe ───────────────────────────────────────

@router.post("/subscribe")
async def subscribe(
    data: SubscribeRequest,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(owner_only()),
    db: AsyncSession = Depends(get_db),
):
    plan = await _get_plan(db, data.plan_key)

    if not plan.stripe_price_id:
        raise ForbiddenException(detail="This plan cannot be subscribed to via Stripe")

    if tenant.plan == data.plan_key and not data.trial:
        raise ForbiddenException(detail=f"You are already on the {data.plan_key} plan")

    customer_id = await _get_or_create_stripe_customer(tenant, current_user, db)

    if tenant.stripe_subscription_id:
        stripe.Subscription.cancel(tenant.stripe_subscription_id)

    session_kwargs = dict(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.APP_BASE_URL}/billing/cancel",
        metadata={"tenant_id": str(tenant.id), "plan_key": data.plan_key},
    )

    if data.trial:
        session_kwargs["subscription_data"] = {"trial_period_days": TRIAL_DAYS}

    session = stripe.checkout.Session.create(**session_kwargs)

    return single({
        "checkout_url": session.url,
        "session_id": session.id,
        "plan": data.plan_key,
        "price_display": f"${plan.price_usd_cents // 100}/mo",
        "trial": data.trial,
        "trial_days": TRIAL_DAYS if data.trial else None,
    })


# ── POST /billing/portal ──────────────────────────────────────────

@router.post("/portal")
async def billing_portal(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(owner_only()),
):
    if not tenant.stripe_customer_id:
        raise ForbiddenException(detail="No billing account found. Please subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=f"{settings.APP_BASE_URL}/billing",
    )
    return single({"portal_url": session.url})


# ── POST /billing/cancel ──────────────────────────────────────────

@router.post("/cancel")
async def cancel_subscription(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(owner_only()),
    db: AsyncSession = Depends(get_db),
):
    if not tenant.stripe_subscription_id:
        raise ForbiddenException(detail="No active subscription to cancel")

    # Cancel at period end — tenant keeps access until billing cycle ends
    stripe.Subscription.modify(
        tenant.stripe_subscription_id,
        cancel_at_period_end=True,
    )

    return single({
        "message": "Subscription will be canceled at the end of the current billing period",
        "plan": tenant.plan,
    })


# ── POST /billing/webhook ─────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info("Stripe webhook: %s", event_type)

    handlers = {
        "checkout.session.completed":       _handle_checkout_completed,
        "invoice.payment_failed":           _handle_payment_failed,
        "invoice.payment_succeeded":        _handle_payment_succeeded,
        "customer.subscription.deleted":    _handle_subscription_deleted,
        "customer.subscription.updated":    _handle_subscription_updated,
        "customer.subscription.trial_will_end": _handle_trial_will_end,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(db, data)

    return JSONResponse({"received": True})


# ── Webhook handlers ──────────────────────────────────────────────

async def _get_tenant_by_customer(db: AsyncSession, customer_id: str) -> Tenant | None:
    result = await db.execute(
        select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def _handle_checkout_completed(db: AsyncSession, session: dict):
    tenant_id = session.get("metadata", {}).get("tenant_id")
    plan_key = session.get("metadata", {}).get("plan_key")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not tenant_id or not plan_key:
        return

    result = await db.execute(select(Tenant).where(Tenant.id == int(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return

    # Check if this is a trial
    sub = stripe.Subscription.retrieve(subscription_id) if subscription_id else None
    status = sub["status"] if sub else "active"
    trial_end = sub.get("trial_end") if sub else None

    tenant.plan = plan_key
    tenant.stripe_customer_id = customer_id
    tenant.stripe_subscription_id = subscription_id
    tenant.stripe_subscription_status = status

    if status == "trialing" and trial_end:
        tenant.trial_ends_at = datetime.fromtimestamp(trial_end, tz=timezone.utc)

    await db.commit()
    logger.info("Tenant %s → %s (%s)", tenant.slug, plan_key, status)


async def _handle_payment_failed(db: AsyncSession, invoice: dict):
    customer_id = invoice.get("customer")
    tenant = await _get_tenant_by_customer(db, customer_id)
    if not tenant:
        return

    tenant.stripe_subscription_status = "past_due"
    tenant.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
    await db.commit()

    # Queue notification email via Celery
    try:
        from app.worker.tasks import send_payment_failed_notification
        send_payment_failed_notification.delay(tenant_id=tenant.id)
    except Exception:
        pass  # don't fail the webhook if task queuing fails

    logger.warning("Payment failed for tenant %s — grace until %s", tenant.slug, tenant.grace_period_ends_at)


async def _handle_payment_succeeded(db: AsyncSession, invoice: dict):
    customer_id = invoice.get("customer")
    tenant = await _get_tenant_by_customer(db, customer_id)
    if not tenant:
        return

    # Clear grace period on successful payment
    tenant.stripe_subscription_status = "active"
    tenant.grace_period_ends_at = None
    await db.commit()
    logger.info("Payment recovered for tenant %s", tenant.slug)


async def _handle_subscription_deleted(db: AsyncSession, subscription: dict):
    customer_id = subscription.get("customer")
    tenant = await _get_tenant_by_customer(db, customer_id)
    if not tenant:
        return

    tenant.plan = "free"
    tenant.stripe_subscription_id = None
    tenant.stripe_subscription_status = "canceled"
    tenant.trial_ends_at = None
    tenant.grace_period_ends_at = None
    await db.commit()
    logger.info("Tenant %s downgraded to free (subscription deleted)", tenant.slug)


async def _handle_subscription_updated(db: AsyncSession, subscription: dict):
    customer_id = subscription.get("customer")
    new_status = subscription.get("status")
    tenant = await _get_tenant_by_customer(db, customer_id)
    if not tenant:
        return

    tenant.stripe_subscription_status = new_status

    if new_status == "active":
        tenant.grace_period_ends_at = None

    await db.commit()


async def _handle_trial_will_end(db: AsyncSession, subscription: dict):
    """Stripe sends this 3 days before trial ends — send reminder email."""
    customer_id = subscription.get("customer")
    tenant = await _get_tenant_by_customer(db, customer_id)
    if not tenant:
        return

    trial_end = subscription.get("trial_end")
    trial_end_dt = datetime.fromtimestamp(trial_end, tz=timezone.utc) if trial_end else None

    try:
        from app.worker.tasks import send_trial_ending_notification
        send_trial_ending_notification.delay(
            tenant_id=tenant.id,
            trial_ends_at=trial_end_dt.isoformat() if trial_end_dt else None,
        )
    except Exception:
        pass

    logger.info("Trial ending soon for tenant %s", tenant.slug)