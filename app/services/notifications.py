# app/services/notifications.py
#
# Typed notification helpers — call these from your route handlers
# after DB writes to broadcast real-time events to tenant members.
#
# Example (in projects route):
#
#   from app.services.notifications import notify
#   await notify.project_created(tenant_id=tenant.id, actor_id=user.id, project=project)

from __future__ import annotations
from typing import Any
from app.core.websocket_manager import manager


class NotificationService:

    # ── Projects ──────────────────────────────────────────────────

    async def project_created(
        self, tenant_id: int, actor_id: int, project: Any
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="project.created",
            actor_id=actor_id,
            data={
                "id": project.id if hasattr(project, "id") else project.get("id"),
                "name": project.name if hasattr(project, "name") else project.get("name"),
            },
        )

    async def project_updated(
        self, tenant_id: int, actor_id: int, project: Any, changes: dict | None = None
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="project.updated",
            actor_id=actor_id,
            data={
                "id": project.id if hasattr(project, "id") else project.get("id"),
                "name": project.name if hasattr(project, "name") else project.get("name"),
                "changes": changes or {},
            },
        )

    async def project_deleted(
        self, tenant_id: int, actor_id: int, project_id: int
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="project.deleted",
            actor_id=actor_id,
            data={"id": project_id},
        )

    # ── Tasks ─────────────────────────────────────────────────────

    async def task_created(
        self, tenant_id: int, actor_id: int, task: Any
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="task.created",
            actor_id=actor_id,
            data={
                "id": task.id if hasattr(task, "id") else task.get("id"),
                "title": task.title if hasattr(task, "title") else task.get("title"),
                "project_id": task.project_id if hasattr(task, "project_id") else task.get("project_id"),
            },
        )

    async def task_updated(
        self, tenant_id: int, actor_id: int, task: Any, changes: dict | None = None
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="task.updated",
            actor_id=actor_id,
            data={
                "id": task.id if hasattr(task, "id") else task.get("id"),
                "title": task.title if hasattr(task, "title") else task.get("title"),
                "project_id": task.project_id if hasattr(task, "project_id") else task.get("project_id"),
                "changes": changes or {},
            },
        )

    async def task_deleted(
        self, tenant_id: int, actor_id: int, task_id: int, project_id: int
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="task.deleted",
            actor_id=actor_id,
            data={"id": task_id, "project_id": project_id},
        )

    # ── Members ───────────────────────────────────────────────────

    async def member_joined(
        self, tenant_id: int, actor_id: int, user: Any
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="member.joined",
            actor_id=actor_id,
            data={
                "id": user.id if hasattr(user, "id") else user.get("id"),
                "email": user.email if hasattr(user, "email") else user.get("email"),
                "role": user.role if hasattr(user, "role") else user.get("role"),
            },
        )

    async def member_removed(
        self, tenant_id: int, actor_id: int, user_id: int, email: str
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="member.removed",
            actor_id=actor_id,
            data={"id": user_id, "email": email},
        )

    async def member_role_changed(
        self, tenant_id: int, actor_id: int, user_id: int, new_role: str
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="member.role_changed",
            actor_id=actor_id,
            data={"id": user_id, "new_role": new_role},
        )

    # ── Billing ───────────────────────────────────────────────────

    async def billing_plan_changed(
        self, tenant_id: int, old_plan: str, new_plan: str
    ) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="billing.plan_changed",
            actor_id=None,
            data={"old_plan": old_plan, "new_plan": new_plan},
        )

    async def billing_payment_failed(self, tenant_id: int) -> None:
        await manager.broadcast(
            tenant_id=tenant_id,
            event="billing.payment_failed",
            actor_id=None,
            data={"message": "Payment failed — grace period started"},
        )


# Singleton
notify = NotificationService()