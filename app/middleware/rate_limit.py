from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from app.core.redis import redis_client


class RateLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        tenant = getattr(request.state, "tenant", None)

        if not tenant:
            return await call_next(request)

        key = f"rate:{tenant.id}"

        count = await redis_client.incr(key)

        if count == 1:
            await redis_client.expire(key, 60)

        if count > 100:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"}
            )

        return await call_next(request)