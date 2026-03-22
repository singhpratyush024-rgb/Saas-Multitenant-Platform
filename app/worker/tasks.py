# app/worker/tasks.py

import os
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import app.models 
from app.models import __init__ 

from celery import shared_task
from sqlalchemy import create_engine, select, delete, func
from sqlalchemy.orm import Session

from app.worker.celery_app import celery_app

load_dotenv()

SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")
logger = logging.getLogger(__name__)


def _get_sync_db() -> Session:
    import app.worker.tasks as _self
    engine = create_engine(_self.SYNC_DATABASE_URL, echo=False)
    return Session(engine)


def _get_redis():
    import redis
    return redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


def _store_task_status(task_id: str, status: str, result=None, error=None):
    import json
    r = _get_redis()
    data = {
        "task_id": task_id,
        "status": status,
        "result": result,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r.setex(f"task_status:{task_id}", 86400, json.dumps(data))


def _send_email_sync(to_email: str, subject: str, html: str) -> None:
    """Send email synchronously inside a Celery task."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.getenv("MAIL_FROM")
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(os.getenv("MAIL_SERVER"), int(os.getenv("MAIL_PORT", 587))) as server:
        server.starttls()
        server.login(os.getenv("MAIL_USERNAME"), os.getenv("MAIL_PASSWORD"))
        server.sendmail(os.getenv("MAIL_FROM"), to_email, msg.as_string())


# ── Task 1: Clean expired invitations ────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.clean_expired_invitations")
def clean_expired_invitations(self):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.invitation import Invitation
        db = _get_sync_db()
        now = datetime.now(timezone.utc)

        stale_cutoff = now - timedelta(hours=24)
        expired_result = db.execute(
            delete(Invitation)
            .where(Invitation.accepted_at.is_(None), Invitation.expires_at < stale_cutoff)
            .returning(Invitation.id)
        )
        expired_count = len(expired_result.fetchall())

        accepted_cutoff = now - timedelta(days=30)
        accepted_result = db.execute(
            delete(Invitation)
            .where(Invitation.accepted_at.is_not(None), Invitation.accepted_at < accepted_cutoff)
            .returning(Invitation.id)
        )
        accepted_count = len(accepted_result.fetchall())

        db.commit()
        db.close()

        result = {"expired_deleted": expired_count, "accepted_deleted": accepted_count, "ran_at": now.isoformat()}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        logger.exception("clean_expired_invitations failed")
        raise


# ── Task 2: Daily digest ──────────────────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.send_daily_digest")
def send_daily_digest(self):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.models.project import Project
        from app.models.task import Task
        from app.models.role import Role

        db = _get_sync_db()
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)
        tenants = db.execute(select(Tenant).where(Tenant.is_active == True)).scalars().all()
        digests_sent = 0

        for tenant in tenants:
            new_projects = db.execute(
                select(func.count(Project.id)).where(Project.tenant_id == tenant.id, Project.created_at >= since)
            ).scalar()
            done_tasks = db.execute(
                select(func.count(Task.id)).where(Task.tenant_id == tenant.id, Task.status == "done", Task.updated_at >= since)
            ).scalar()

            if new_projects == 0 and done_tasks == 0:
                continue

            owner_role = db.execute(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
            ).scalar_one_or_none()
            if not owner_role:
                continue

            owners = db.execute(
                select(User).where(User.tenant_id == tenant.id, User.role_id == owner_role.id)
            ).scalars().all()

            for owner in owners:
                logger.info("Daily digest for %s → %s: %d projects, %d tasks done",
                           tenant.name, owner.email, new_projects, done_tasks)
                digests_sent += 1

        db.close()
        result = {"digests_sent": digests_sent, "ran_at": now.isoformat()}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        logger.exception("send_daily_digest failed")
        raise


# ── Task 3: Collect usage stats ───────────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.collect_usage_stats")
def collect_usage_stats(self):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        import json
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.models.project import Project
        from app.models.task import Task

        db = _get_sync_db()
        r = _get_redis()
        now = datetime.now(timezone.utc)
        tenants = db.execute(select(Tenant).where(Tenant.is_active == True)).scalars().all()
        stats_collected = 0

        for tenant in tenants:
            stats = {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "total_members": db.execute(select(func.count(User.id)).where(User.tenant_id == tenant.id)).scalar(),
                "total_projects": db.execute(select(func.count(Project.id)).where(Project.tenant_id == tenant.id)).scalar(),
                "total_tasks": db.execute(select(func.count(Task.id)).where(Task.tenant_id == tenant.id)).scalar(),
                "tasks_done": db.execute(select(func.count(Task.id)).where(Task.tenant_id == tenant.id, Task.status == "done")).scalar(),
                "collected_at": now.isoformat(),
            }
            r.setex(f"usage_stats:tenant:{tenant.id}", 90000, json.dumps(stats))
            stats_collected += 1

        db.close()
        result = {"tenants_processed": stats_collected, "ran_at": now.isoformat()}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        logger.exception("collect_usage_stats failed")
        raise


# ── Task 4: Send email async ──────────────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.send_email_async", max_retries=3, default_retry_delay=60)
def send_email_async(self, *, to_email: str, subject: str, html: str):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        _send_email_sync(to_email, subject, html)
        result = {"to": to_email, "subject": subject}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        raise self.retry(exc=e)


# ── Task 5: Auto-downgrade expired trials ─────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.auto_downgrade_expired_trials")
def auto_downgrade_expired_trials(self):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.tenant import Tenant
        db = _get_sync_db()
        now = datetime.now(timezone.utc)

        expired_trials = db.execute(
            select(Tenant).where(
                Tenant.stripe_subscription_status == "trialing",
                Tenant.trial_ends_at != None,
                Tenant.trial_ends_at < now,
            )
        ).scalars().all()

        downgraded = 0
        for tenant in expired_trials:
            tenant.plan = "free"
            tenant.stripe_subscription_status = "canceled"
            tenant.stripe_subscription_id = None
            tenant.trial_ends_at = None
            logger.info("Auto-downgraded expired trial: tenant %s", tenant.slug)
            downgraded += 1

        db.commit()
        db.close()

        result = {"downgraded": downgraded, "ran_at": now.isoformat()}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        logger.exception("auto_downgrade_expired_trials failed")
        raise


# ── Task 6: Auto-downgrade expired grace periods ──────────────────

@celery_app.task(bind=True, name="app.worker.tasks.auto_downgrade_expired_grace_periods")
def auto_downgrade_expired_grace_periods(self):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.tenant import Tenant
        db = _get_sync_db()
        now = datetime.now(timezone.utc)

        expired_grace = db.execute(
            select(Tenant).where(
                Tenant.stripe_subscription_status == "past_due",
                Tenant.grace_period_ends_at != None,
                Tenant.grace_period_ends_at < now,
            )
        ).scalars().all()

        downgraded = 0
        for tenant in expired_grace:
            tenant.plan = "free"
            tenant.stripe_subscription_status = "canceled"
            tenant.stripe_subscription_id = None
            tenant.grace_period_ends_at = None
            logger.warning("Auto-downgraded after grace period: tenant %s", tenant.slug)
            downgraded += 1

        db.commit()
        db.close()

        result = {"downgraded": downgraded, "ran_at": now.isoformat()}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        logger.exception("auto_downgrade_expired_grace_periods failed")
        raise


# ── Task 7: Payment failed notification ──────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.send_payment_failed_notification", max_retries=3)
def send_payment_failed_notification(self, *, tenant_id: int):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.models.role import Role

        db = _get_sync_db()
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            return

        owner_role = db.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
        ).scalar_one_or_none()
        if not owner_role:
            return

        owners = db.execute(
            select(User).where(User.tenant_id == tenant.id, User.role_id == owner_role.id)
        ).scalars().all()

        grace_end = tenant.grace_period_ends_at
        grace_str = grace_end.strftime("%B %d, %Y") if grace_end else "soon"

        for owner in owners:
            html = f"""
            <h2>Payment Failed for {tenant.name}</h2>
            <p>Hi {owner.email},</p>
            <p>We were unable to process your payment for the <strong>{tenant.plan.title()}</strong> plan.</p>
            <p>You have a <strong>7-day grace period</strong> until <strong>{grace_str}</strong>
               to update your payment method before your account is downgraded to the Free plan.</p>
            <p><a href="{os.getenv('APP_BASE_URL', '')}/billing/portal">Update Payment Method</a></p>
            """
            _send_email_sync(owner.email, f"Payment Failed — Action Required ({tenant.name})", html)
            logger.info("Sent payment failed notification to %s", owner.email)

        db.close()
        result = {"tenant_id": tenant_id, "notified": len(owners)}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        raise self.retry(exc=e)


# ── Task 8: Trial ending notification ────────────────────────────

@celery_app.task(bind=True, name="app.worker.tasks.send_trial_ending_notification", max_retries=3)
def send_trial_ending_notification(self, *, tenant_id: int, trial_ends_at: str | None):
    task_id = self.request.id
    _store_task_status(task_id, "STARTED")
    try:
        from app.models.tenant import Tenant
        from app.models.user import User
        from app.models.role import Role

        db = _get_sync_db()
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            return

        owner_role = db.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
        ).scalar_one_or_none()
        if not owner_role:
            return

        owners = db.execute(
            select(User).where(User.tenant_id == tenant.id, User.role_id == owner_role.id)
        ).scalars().all()

        end_str = trial_ends_at or "soon"

        for owner in owners:
            html = f"""
            <h2>Your trial ends in 3 days</h2>
            <p>Hi {owner.email},</p>
            <p>Your free trial of <strong>{tenant.plan.title()}</strong> for <strong>{tenant.name}</strong>
               ends on <strong>{end_str}</strong>.</p>
            <p>To keep access to all features, please add a payment method before your trial ends.</p>
            <p><a href="{os.getenv('APP_BASE_URL', '')}/billing">Manage Billing</a></p>
            """
            _send_email_sync(owner.email, f"Your trial ends in 3 days — {tenant.name}", html)
            logger.info("Sent trial ending notification to %s", owner.email)

        db.close()
        result = {"tenant_id": tenant_id, "notified": len(owners)}
        _store_task_status(task_id, "SUCCESS", result=result)
        return result
    except Exception as e:
        _store_task_status(task_id, "FAILURE", error=str(e))
        raise self.retry(exc=e)