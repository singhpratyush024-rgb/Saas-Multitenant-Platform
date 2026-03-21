# app/api/router.py
#
# Routes are served at TWO prefixes simultaneously:
#   - Original paths (/auth, /projects, etc.)  — keeps all existing tests passing
#   - Versioned paths (/api/v1/auth, etc.)      — new standard for API clients
#
# WebSocket and health stay unversioned always.

from fastapi import APIRouter

from app.api.routes import auth
from app.api.routes import project
from app.api.routes import health
from app.api.routes import invitations
from app.api.routes import members
from app.api.routes import tasks
from app.api.routes import uploads
from app.api.routes import search
from app.api.routes import task_status
from app.api.routes import billing
from app.api.routes import websocket

# ── Top-level router ──────────────────────────────────────────────
router = APIRouter()

# Health + WebSocket — unversioned always
router.include_router(health.router)
router.include_router(websocket.router)

# ── Original paths (no prefix) — keeps ALL existing tests passing ─
router.include_router(auth.router)
router.include_router(project.router)
router.include_router(invitations.router)
router.include_router(members.router)
router.include_router(tasks.router)
router.include_router(uploads.router)
router.include_router(search.router)
router.include_router(search.audit_router)
router.include_router(task_status.router)
router.include_router(billing.router)

# ── Versioned paths (/api/v1/) — for new API clients ─────────────
v1 = APIRouter(prefix="/api/v1")
v1.include_router(auth.router)
v1.include_router(project.router)
v1.include_router(invitations.router)
v1.include_router(members.router)
v1.include_router(tasks.router)
v1.include_router(uploads.router)
v1.include_router(search.router)
v1.include_router(search.audit_router)
v1.include_router(task_status.router)
v1.include_router(billing.router)

router.include_router(v1)