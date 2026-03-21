# app/core/websocket_manager.py
#
# Tenant-scoped WebSocket connection manager.
#
# Each tenant gets its own "room". When a resource changes, broadcast
# to all connected clients in that tenant's room only.
#
# Usage (from a route or service):
#
#   from app.core.websocket_manager import manager
#   await manager.broadcast(tenant_id=42, event="project.created", data={...})

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TenantConnectionManager:
    """
    Maintains a mapping of tenant_id → set of active WebSocket connections.
    Thread-safe for asyncio (single-threaded event loop).
    """

    def __init__(self) -> None:
        # tenant_id (int) → set of WebSocket objects
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)

    # ── Lifecycle ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket, tenant_id: int) -> None:
        await websocket.accept()
        self._rooms[tenant_id].add(websocket)
        logger.info(
            "WS connected | tenant=%s | total_in_room=%s",
            tenant_id,
            len(self._rooms[tenant_id]),
        )

    def disconnect(self, websocket: WebSocket, tenant_id: int) -> None:
        self._rooms[tenant_id].discard(websocket)
        if not self._rooms[tenant_id]:
            del self._rooms[tenant_id]
        logger.info("WS disconnected | tenant=%s", tenant_id)

    # ── Broadcasting ──────────────────────────────────────────────

    async def broadcast(
        self,
        tenant_id: int,
        event: str,
        data: dict[str, Any],
        actor_id: int | None = None,
    ) -> None:
        """
        Send a JSON event to all connections in the tenant's room.

        Payload shape:
            {
                "event": "project.created",
                "data": { ... },
                "actor_id": 123         # user who triggered the event
            }
        """
        if tenant_id not in self._rooms:
            return

        payload = json.dumps(
            {"event": event, "data": data, "actor_id": actor_id}
        )

        dead: list[WebSocket] = []
        for ws in list(self._rooms[tenant_id]):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Prune broken connections
        for ws in dead:
            self.disconnect(ws, tenant_id)

    async def broadcast_to_user(
        self,
        websocket: WebSocket,
        event: str,
        data: dict[str, Any],
    ) -> None:
        """Send a private message to a single connection."""
        try:
            await websocket.send_text(
                json.dumps({"event": event, "data": data})
            )
        except Exception:
            pass

    # ── Introspection ─────────────────────────────────────────────

    def connection_count(self, tenant_id: int) -> int:
        return len(self._rooms.get(tenant_id, set()))

    def total_connections(self) -> int:
        return sum(len(s) for s in self._rooms.values())


# Singleton — import this everywhere
manager = TenantConnectionManager()