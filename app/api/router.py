# app/api/router.py

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

router = APIRouter()

router.include_router(auth.router)
router.include_router(project.router)
router.include_router(health.router)
router.include_router(invitations.router)
router.include_router(members.router)
router.include_router(tasks.router)
router.include_router(uploads.router)
router.include_router(search.router)
router.include_router(search.audit_router)
router.include_router(task_status.router)
router.include_router(billing.router)