# app/api/routes/task_status.py
#
# Polling endpoint for Celery task status.
# GET /tasks/{task_id}/status
#
# Also exposes:
# POST /tasks/trigger/{task_name} — manually trigger a periodic task
# GET /tasks/stats/{tenant_id}   — get cached usage stats

import json
from fastapi import APIRouter, Depends, HTTPException, Path
from app.core.redis import redis_client
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_current_tenant
from app.dependencies.permission import admin_or_owner
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.response import single

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── GET /tasks/{task_id}/status ───────────────────────────────────

@router.get("/{task_id}/status")
async def get_task_status(
    task_id: str = Path(..., description="Celery task ID"),
    current_user: User = Depends(get_current_user),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Poll the status of a Celery background task.

    States:
    - PENDING  — task queued, not yet picked up
    - STARTED  — worker has started processing
    - SUCCESS  — completed successfully, result available
    - FAILURE  — task failed, error available
    - RETRY    — being retried after failure
    """
    # Check our Redis status store first (set by tasks themselves)
    raw = await redis_client.get(f"task_status:{task_id}")
    if raw:
        return single(json.loads(raw))

    # Fall back to Celery's own result backend
    try:
        from app.worker.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)

        return single({
            "task_id": task_id,
            "status": result.state,
            "result": result.result if result.successful() else None,
            "error": str(result.result) if result.failed() else None,
        })
    except Exception:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


# ── POST /tasks/trigger/{task_name} — manually trigger a task ────

ALLOWED_TASKS = {
    "clean_expired_invitations": "app.worker.tasks.clean_expired_invitations",
    "send_daily_digest":         "app.worker.tasks.send_daily_digest",
    "collect_usage_stats":       "app.worker.tasks.collect_usage_stats",
}


@router.post("/trigger/{task_name}")
async def trigger_task(
    task_name: str,
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(admin_or_owner()),
):
    """
    Manually trigger a periodic task (admin/owner only).
    Useful for testing and on-demand runs.
    """
    if task_name not in ALLOWED_TASKS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task '{task_name}'. Allowed: {list(ALLOWED_TASKS.keys())}",
        )

    from app.worker.celery_app import celery_app
    result = celery_app.send_task(ALLOWED_TASKS[task_name])

    return single({
        "task_id": result.id,
        "task_name": task_name,
        "status": "QUEUED",
        "poll_url": f"/tasks/{result.id}/status",
    })


# ── GET /tasks/stats/me — usage stats for current tenant ─────────

@router.get("/stats/me")
async def get_usage_stats(
    tenant: Tenant = Depends(get_current_tenant),
    current_user: User = Depends(admin_or_owner()),
):
    """Return the latest cached usage stats for this tenant."""
    raw = await redis_client.get(f"usage_stats:tenant:{tenant.id}")
    if not raw:
        return single({
            "message": "Stats not yet collected. "
                       "Trigger collect_usage_stats or wait for the nightly run.",
            "tenant_id": tenant.id,
        })
    return single(json.loads(raw))