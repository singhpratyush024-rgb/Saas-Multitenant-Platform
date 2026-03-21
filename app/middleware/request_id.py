# app/middleware/request_id.py
#
# Attaches a unique X-Request-ID to every request/response.
# The ID is available via request.state.request_id throughout the
# request lifecycle (e.g. in exception handlers and log statements).
#
# If the client sends an X-Request-ID header, that value is reused
# (useful for distributed tracing / end-to-end correlation).

import uuid
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        # Reuse client-supplied ID or generate a new one
        request_id = (
            request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id

        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Propagate ID back to client + expose timing
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)

        logger.info(
            "REQUEST | %s %s | status=%s | %sms | id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        return response