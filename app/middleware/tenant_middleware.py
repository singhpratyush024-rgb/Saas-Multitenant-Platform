# app/middleware/tenant_middleware.py
#
# Middleware now ONLY validates the header is present.
# Actual tenant DB lookup is done in get_current_tenant dependency
# using the same get_db session as the rest of the app.

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import TenantHeaderMissingException


class TenantMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        tenant_slug = request.headers.get("X-Tenant-ID")

        # Only check header presence here — DB lookup moved to dependency
        if not tenant_slug:
            exc = TenantHeaderMissingException()
            return JSONResponse(
                status_code=exc.status_code,
                content={"success": False, "detail": exc.detail},
            )

        response = await call_next(request)
        return response