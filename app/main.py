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

    # Redis check
    try:
        await redis_client.ping()
        print("Redis connected successfully")
    except Exception as e:
        print("Redis connection failed:", e)

    # Seed plans
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


app = FastAPI(
    lifespan=lifespan,
    title="SaaS Multi-Tenant API",
    version="1.0.0",
)

# ── Exception handlers ───────────────────────────────────────────
register_exception_handlers(app)

# ── Middleware ───────────────────────────────────────────────────
app.add_middleware(TenantMiddleware)
app.add_middleware(RateLimitMiddleware)

# ── Routes ──────────────────────────────────────────────────────
app.include_router(router)


@app.get("/")
def root():
    return {"message": "SaaS Multi-Tenant API running"}