# tests/test_integration.py
#
# Integration tests — full flows across multiple components:
# invite flow, Stripe webhook mocks, worker task execution

import pytest
import json
import secrets
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import select, delete

from app.models.user import User
from app.models.invitation import Invitation
from app.models.project import Project
from app.models.task import Task
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.plan import Plan


# ══════════════════════════════════════════════════════════════════
# Invite Flow — full end to end
# ══════════════════════════════════════════════════════════════════

class TestInviteFlow:

    @pytest.mark.asyncio
    async def test_full_invite_accept_flow(
        self, owner_client, acme_client, db, tenant, member_role
    ):
        """
        Owner creates invitation → invitee accepts →
        new user exists with correct role.
        """
        invite_email = "full_flow_invite@acme.com"

        # Clean up
        await db.execute(delete(User).where(User.email == invite_email))
        await db.execute(
            delete(Invitation).where(
                Invitation.email == invite_email,
                Invitation.tenant_id == tenant.id,
            )
        )
        await db.commit()

        # Step 1: Owner creates invitation
        res = await owner_client.post(
            "/invitations/",
            json={"email": invite_email, "role_id": member_role.id},
        )
        assert res.status_code == 200
        invite_id = res.json()["id"]

        # Step 2: Fetch token from DB
        inv = (await db.execute(
            select(Invitation).where(Invitation.id == invite_id)
        )).scalar_one()
        token = inv.token

        # Step 3: Accept invitation (no auth needed)
        res = await acme_client.post(
            "/invitations/accept",
            json={"token": token, "password": "newpassword123"},
        )
        assert res.status_code == 200
        assert "Account created" in res.json()["message"]

        # Step 4: Verify user exists with correct role
        user = (await db.execute(
            select(User).where(User.email == invite_email, User.tenant_id == tenant.id)
        )).scalar_one_or_none()
        assert user is not None
        assert user.role == "member"
        assert user.role_id == member_role.id

        # Step 5: Verify invitation marked as accepted
        await db.refresh(inv)
        assert inv.accepted_at is not None

        # Cleanup
        await db.delete(user)
        await db.delete(inv)
        await db.commit()

    @pytest.mark.asyncio
    async def test_invite_expired_token_rejected(self, acme_client, db, tenant, member_role):
        """Expired invitation cannot be accepted."""
        expired_token = secrets.token_urlsafe(32)
        inv = Invitation(
            email="expired_invite@acme.com",
            tenant_id=tenant.id,
            role_id=member_role.id,
            token=expired_token,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(inv)
        await db.commit()

        res = await acme_client.post(
            "/invitations/accept",
            json={"token": expired_token, "password": "password123"},
        )
        assert res.status_code == 410

        await db.delete(inv)
        await db.commit()

    @pytest.mark.asyncio
    async def test_invite_cannot_invite_existing_member(
        self, owner_client, member_user, member_role
    ):
        res = await owner_client.post(
            "/invitations/",
            json={"email": member_user.email, "role_id": member_role.id},
        )
        assert res.status_code == 400
        assert "already a member" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_invite_resend_refreshes_expired(
        self, owner_client, db, tenant, member_role
    ):
        """Resending an expired invite generates a new token and extends expiry."""
        old_token = secrets.token_urlsafe(32)
        inv = Invitation(
            email="resend_test@acme.com",
            tenant_id=tenant.id,
            role_id=member_role.id,
            token=old_token,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(inv)
        await db.commit()

        from app.core.redis import redis_client
        await redis_client.delete(f"resend_invite:{inv.id}")

        res = await owner_client.post(f"/invitations/{inv.id}/resend")
        assert res.status_code == 200

        await db.refresh(inv)
        assert inv.token != old_token
        assert inv.expires_at > datetime.now(timezone.utc)

        await db.delete(inv)
        await db.commit()


# ══════════════════════════════════════════════════════════════════
# Stripe Webhook Integration
# ══════════════════════════════════════════════════════════════════

class TestStripeWebhooks:

    def _webhook_payload(self, event_type: str, data: dict) -> bytes:
        return json.dumps({
            "type": event_type,
            "data": {"object": data},
        }).encode()

    @pytest.mark.asyncio
    async def test_checkout_completed_upgrades_plan(
        self, http_client, db, tenant
    ):
        original_plan = tenant.plan
        tenant.stripe_customer_id = "cus_webhook_integ"
        await db.commit()

        payload = self._webhook_payload("checkout.session.completed", {
            "metadata": {"tenant_id": str(tenant.id), "plan_key": "pro"},
            "subscription": "sub_integ_001",
            "customer": "cus_webhook_integ",
        })

        with patch("stripe.Webhook.construct_event") as mock_event, \
             patch("stripe.Subscription.retrieve") as mock_sub:
            mock_event.return_value = json.loads(payload)
            mock_sub.return_value = {"status": "active", "trial_end": None}

            res = await http_client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert res.status_code == 200

        await db.refresh(tenant)
        assert tenant.plan == "pro"
        assert tenant.stripe_subscription_status == "active"

        # Reset
        tenant.plan = original_plan
        tenant.stripe_customer_id = None
        tenant.stripe_subscription_id = None
        tenant.stripe_subscription_status = None
        await db.commit()

    @pytest.mark.asyncio
    async def test_payment_failed_sets_grace_period(
        self, http_client, db, tenant
    ):
        tenant.stripe_customer_id = "cus_grace_integ"
        tenant.plan = "pro"
        tenant.stripe_subscription_status = "active"
        await db.commit()

        payload = self._webhook_payload("invoice.payment_failed", {
            "customer": "cus_grace_integ",
        })

        with patch("stripe.Webhook.construct_event") as mock_event, \
             patch("app.worker.tasks.send_payment_failed_notification.delay"):
            mock_event.return_value = json.loads(payload)
            res = await http_client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=1,v1=test"},
            )

        assert res.status_code == 200
        await db.refresh(tenant)
        assert tenant.stripe_subscription_status == "past_due"
        assert tenant.grace_period_ends_at is not None
        assert tenant.plan == "pro"  # still on pro during grace

        # Reset
        tenant.plan = "free"
        tenant.stripe_customer_id = None
        tenant.stripe_subscription_id = None
        tenant.stripe_subscription_status = None
        tenant.grace_period_ends_at = None
        await db.commit()

    @pytest.mark.asyncio
    async def test_subscription_deleted_downgrades_to_free(
        self, http_client, db, tenant
    ):
        tenant.stripe_customer_id = "cus_delete_integ"
        tenant.plan = "starter"
        tenant.stripe_subscription_id = "sub_delete_integ"
        tenant.stripe_subscription_status = "active"
        await db.commit()

        payload = self._webhook_payload("customer.subscription.deleted", {
            "customer": "cus_delete_integ",
            "status": "canceled",
        })

        with patch("stripe.Webhook.construct_event") as mock_event:
            mock_event.return_value = json.loads(payload)
            res = await http_client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=1,v1=test"},
            )

        assert res.status_code == 200
        await db.refresh(tenant)
        assert tenant.plan == "free"
        assert tenant.stripe_subscription_status == "canceled"

        # Reset
        tenant.stripe_customer_id = None
        tenant.stripe_subscription_id = None
        tenant.stripe_subscription_status = None
        await db.commit()

    @pytest.mark.asyncio
    async def test_invalid_webhook_signature_rejected(self, http_client):
        payload = b'{"type": "checkout.session.completed", "data": {"object": {}}}'

        with patch("stripe.Webhook.construct_event") as mock_event:
            import stripe
            mock_event.side_effect = stripe.error.SignatureVerificationError(
                "Invalid signature", "sig_header"
            )
            res = await http_client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=bad,v1=invalid"},
            )
        assert res.status_code == 400


# ══════════════════════════════════════════════════════════════════
# Worker Task Integration
# ══════════════════════════════════════════════════════════════════

class TestWorkerTasks:

    def _patch_sync_url(self):
        import os
        return os.environ["SYNC_DATABASE_URL"]

    @pytest.mark.asyncio
    async def test_clean_expired_invitations_runs(self):
        import app.worker.tasks as task_module
        original = task_module.SYNC_DATABASE_URL
        task_module.SYNC_DATABASE_URL = self._patch_sync_url()
        try:
            from app.worker.tasks import clean_expired_invitations
            result = clean_expired_invitations.apply().get()
            assert "expired_deleted" in result
            assert "ran_at" in result
        finally:
            task_module.SYNC_DATABASE_URL = original

    @pytest.mark.asyncio
    async def test_collect_usage_stats_populates_redis(self, owner_client, tenant):
        import app.worker.tasks as task_module
        original = task_module.SYNC_DATABASE_URL
        task_module.SYNC_DATABASE_URL = self._patch_sync_url()
        try:
            from app.worker.tasks import collect_usage_stats
            result = collect_usage_stats.apply().get()
            assert result["tenants_processed"] >= 1
        finally:
            task_module.SYNC_DATABASE_URL = original

        # Verify stats are accessible via API
        res = await owner_client.get("/tasks/stats/me")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "total_members" in data or "message" in data

    @pytest.mark.asyncio
    async def test_auto_downgrade_expired_trials(self, db, tenant):
        """Set a tenant to trialing with expired trial, verify task downgrades it."""
        tenant.plan = "starter"
        tenant.stripe_subscription_status = "trialing"
        tenant.trial_ends_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db.commit()

        import app.worker.tasks as task_module
        original = task_module.SYNC_DATABASE_URL
        task_module.SYNC_DATABASE_URL = self._patch_sync_url()
        try:
            from app.worker.tasks import auto_downgrade_expired_trials
            result = auto_downgrade_expired_trials.apply().get()
            assert result["downgraded"] >= 1
        finally:
            task_module.SYNC_DATABASE_URL = original

        await db.refresh(tenant)
        assert tenant.plan == "free"
        assert tenant.trial_ends_at is None

    @pytest.mark.asyncio
    async def test_task_status_polling(self, owner_client):
        """Trigger a task and verify status polling works."""
        res = await owner_client.post("/tasks/trigger/collect_usage_stats")
        assert res.status_code == 200
        data = res.json()["data"]
        task_id = data["task_id"]
        assert "poll_url" in data

        status_res = await owner_client.get(f"/tasks/{task_id}/status")
        assert status_res.status_code == 200
        assert status_res.json()["data"]["task_id"] == task_id


# ══════════════════════════════════════════════════════════════════
# Audit Log Integration
# ══════════════════════════════════════════════════════════════════

class TestAuditLog:

    @pytest.mark.asyncio
    async def test_project_create_logged(self, owner_client, db, tenant):
        res = await owner_client.post(
            "/projects/",
            json={"name": "Audit Create Test"},
        )
        assert res.status_code == 200
        project_id = res.json()["data"]["id"]

        logs = (await db.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.resource_type == "project",
                AuditLog.action == "create",
                AuditLog.resource_id == project_id,
            )
        )).scalars().all()
        assert len(logs) >= 1
        assert logs[0].diff["after"]["name"] == "Audit Create Test"

    @pytest.mark.asyncio
    async def test_project_update_logged_with_diff(self, owner_client, db, tenant):
        create = await owner_client.post(
            "/projects/",
            json={"name": "Before Update"},
        )
        pid = create.json()["data"]["id"]

        await owner_client.patch(f"/projects/{pid}", json={"name": "After Update"})

        logs = (await db.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.resource_type == "project",
                AuditLog.action == "update",
                AuditLog.resource_id == pid,
            )
        )).scalars().all()
        assert len(logs) >= 1
        assert logs[0].diff["before"]["name"] == "Before Update"
        assert logs[0].diff["after"]["name"] == "After Update"

    @pytest.mark.asyncio
    async def test_audit_logs_api_returns_entries(self, owner_client):
        # Create something to audit
        await owner_client.post("/projects/", json={"name": "Audit API Test"})

        res = await owner_client.get("/audit-logs/")
        assert res.status_code == 200
        logs = res.json()["data"]
        assert isinstance(logs, list)
        assert len(logs) >= 1

    @pytest.mark.asyncio
    async def test_audit_logs_filtered_by_resource_type(self, owner_client):
        res = await owner_client.get("/audit-logs/?resource_type=project")
        assert res.status_code == 200
        logs = res.json()["data"]
        assert all(log["resource_type"] == "project" for log in logs)