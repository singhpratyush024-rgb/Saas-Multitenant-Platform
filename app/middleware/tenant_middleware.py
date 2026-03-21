# app/middleware/tenant_middleware.py

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import TenantHeaderMissingException

# Paths that do not require X-Tenant-ID header
EXEMPT_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/invitations/accept",
    "/billing/webhook",    # Stripe webhook — no tenant header
}


class TenantMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        tenant_slug = request.headers.get("X-Tenant-ID")

        if not tenant_slug:
            exc = TenantHeaderMissingException()
            return JSONResponse(
                status_code=exc.status_code,
                content={"success": False, "detail": exc.detail},
            )

        response = await call_next(request)
        return response