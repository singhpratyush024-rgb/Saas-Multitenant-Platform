# app/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.redis import redis_client
from app.core.exception_handlers import register_exception_handlers
from app.middleware.tenant_middleware import TenantMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.api.router import router


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting application")

    try:
        await redis_client.ping()
        print("Redis connected successfully")
    except Exception as e:
        print("Redis connection failed:", e)

    try:
        from app.core.database import get_db
        from app.services.seed_plans import seed_plans
        async for db in get_db():
            await seed_plans(db)
            print("Plans seeded successfully")
            break
    except Exception as e:
        print("Plan seeding failed:", e)

    yield
    print("Shutting down")


# ── OpenAPI metadata ──────────────────────────────────────────────

DESCRIPTION = """
## SaaS Multi-Tenant API

A fully-featured multi-tenant SaaS backend with:

- **JWT authentication** with refresh tokens and token blacklisting
- **Role-based access control** (owner / admin / member)
- **Tenant isolation** — every resource is scoped to a tenant
- **Billing** via Stripe with webhooks, trials, and grace periods
- **Real-time notifications** via WebSocket (tenant-scoped rooms)
- **Background tasks** via Celery + Redis
- **Audit logging** on all resource mutations

### Authentication

All endpoints (except `/api/v1/auth/*` and `/health`) require:
- `Authorization: Bearer <token>` header
- `X-Tenant-ID: <tenant-slug>` header

### WebSocket

Connect at `ws://<host>/ws/connect?token=<JWT>&tenant=<slug>`
"""

TAGS_METADATA = [
    {
        "name": "auth",
        "description": "Register, login, logout, token refresh.",
    },
    {
        "name": "projects",
        "description": "CRUD for projects. Members can read/write; only admin/owner can delete.",
    },
    {
        "name": "tasks",
        "description": "Task management scoped to projects.",
    },
    {
        "name": "members",
        "description": "List, update roles, and remove tenant members.",
    },
    {
        "name": "invitations",
        "description": "Invite new users to a tenant via email token.",
    },
    {
        "name": "billing",
        "description": "Stripe-backed subscription management, usage, and invoices.",
    },
    {
        "name": "search",
        "description": "Full-text search across projects and tasks.",
    },
    {
        "name": "audit",
        "description": "Immutable audit log of all resource mutations (owner/admin only).",
    },
    {
        "name": "uploads",
        "description": "File upload and retrieval scoped to tenant.",
    },
    {
        "name": "task_status",
        "description": "Poll Celery task status by task ID.",
    },
    {
        "name": "websocket",
        "description": "Real-time WebSocket connection endpoint (tenant-scoped).",
    },
    {
        "name": "health",
        "description": "Health check — no auth required.",
    },
]


# ── App factory ───────────────────────────────────────────────────

app = FastAPI(
    lifespan=lifespan,
    title="SaaS Multi-Tenant API",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "Private",
    },
)

# ── Exception handlers ────────────────────────────────────────────
register_exception_handlers(app)

# ── Middleware (applied bottom-up — last added = outermost) ───────

# 1. GZip — compress responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        # Add your production frontend domains here:
        # "https://app.yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Request-ID",
        "X-Response-Time-Ms",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)

# 3. Request ID tracing (runs before tenant/rate-limit so ID is available in handlers)
app.add_middleware(RequestIDMiddleware)

# 4. Tenant resolution
app.add_middleware(TenantMiddleware)

# 5. Rate limiting
app.add_middleware(RateLimitMiddleware)

# ── Routes ────────────────────────────────────────────────────────
app.include_router(router)


# ── Root ──────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "SaaS Multi-Tenant API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }