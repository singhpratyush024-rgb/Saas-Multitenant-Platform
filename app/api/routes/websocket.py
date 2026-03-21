# app/api/routes/websocket.py
#
# WebSocket endpoint — tenant-scoped, JWT-authenticated.
#
# Connect:
#   ws://host/ws/connect?token=<JWT>&tenant=<slug>
#
# On connect the server sends:
#   {"event": "connected", "data": {"tenant_id": 1, "user_id": 42}}
#
# Server pushes events as:
#   {"event": "project.created", "data": {...}, "actor_id": 42}
#
# Client can send a ping to keep the connection alive:
#   {"type": "ping"}  →  {"event": "pong", "data": {}}

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.core.websocket_manager import manager
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _get_db_session() -> AsyncSession:
    """Helper — grab a one-shot DB session outside of Depends."""
    async for session in get_db():
        return session


@router.websocket("/ws/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    tenant: str = Query(..., description="Tenant slug (X-Tenant-ID equivalent)"),
):
    """
    Authenticate via JWT query param, resolve tenant, then hold the
    connection open broadcasting real-time events scoped to that tenant.
    """
    db = await _get_db_session()

    # ── Auth ──────────────────────────────────────────────────────
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload.get("user_id")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        await websocket.close(code=4001, reason="User not found")
        return

    # ── Tenant resolution + isolation ────────────────────────────
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.slug == tenant)
    )
    tenant_obj = tenant_result.scalar_one_or_none()

    if not tenant_obj:
        await websocket.close(code=4004, reason="Tenant not found")
        return

    if user.tenant_id != tenant_obj.id:
        await websocket.close(code=4003, reason="Forbidden — wrong tenant")
        return

    if not tenant_obj.is_active:
        await websocket.close(code=4003, reason="Tenant inactive")
        return

    # ── Connect ───────────────────────────────────────────────────
    await manager.connect(websocket, tenant_obj.id)
    await manager.broadcast_to_user(
        websocket,
        event="connected",
        data={
            "tenant_id": tenant_obj.id,
            "tenant_slug": tenant_obj.slug,
            "user_id": user.id,
            "user_email": user.email,
            "connections_in_room": manager.connection_count(tenant_obj.id),
        },
    )

    try:
        while True:
            # Keep the connection alive; handle client-sent pings
            msg = await websocket.receive_text()
            try:
                import json
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await manager.broadcast_to_user(
                        websocket, event="pong", data={}
                    )
            except Exception:
                pass  # ignore malformed client messages

    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_obj.id)
        logger.info("WS disconnected cleanly | user=%s tenant=%s", user_id, tenant)
    except Exception as exc:
        manager.disconnect(websocket, tenant_obj.id)
        logger.warning("WS error | user=%s | %s", user_id, exc)