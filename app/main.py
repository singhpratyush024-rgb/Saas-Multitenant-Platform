# app/main.py

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.core.redis import redis_client
from app.api.router import router
from app.middleware.tenant_middleware import TenantMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.core.exception_handlers import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting application")
    try:
        await redis_client.ping()
        print("Redis connected successfully")
    except Exception as e:
        print("Redis connection failed:", e)
    yield
    print("Shutting down")


app = FastAPI(
    lifespan=lifespan,
    title="SaaS Multi-Tenant API",
    version="1.0.0",
)

# ── Exception handlers (must be before middleware) ──────────────────
register_exception_handlers(app)

# ── Middleware ───────────────────────────────────────────────────────
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware)

# ── Routes ──────────────────────────────────────────────────────────
app.include_router(router)


@app.get("/")
def root():
    return {"message": "SaaS Multi-Tenant API running"}