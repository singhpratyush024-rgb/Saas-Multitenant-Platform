# app/core/exception_handlers.py
#
# Structured JSON error responses for all exception types.
# Every response includes the X-Request-ID if available.
#
# Response shape (always):
#   {
#     "success": false,
#     "detail": "Human-readable message",
#     "code": "ERROR_CODE",          # machine-readable
#     "request_id": "uuid"           # from RequestIDMiddleware
#   }

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppBaseException as AppException

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────

def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    request: Request,
    status_code: int,
    detail: str,
    code: str = "ERROR",
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "success": False,
        "detail": detail,
        "code": code,
        "request_id": _request_id(request),
    }
    if extra:
        body.update(extra)

    headers = {}
    rid = _request_id(request)
    if rid:
        headers["X-Request-ID"] = rid

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=headers,
    )


# ── Handlers ──────────────────────────────────────────────────────

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "App exception | %s %s | %s %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return _error_response(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
        code=exc.__class__.__name__.upper().replace("EXCEPTION", ""),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "HTTP exception | %s %s | %s %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return _error_response(
        request,
        status_code=exc.status_code,
        detail=str(exc.detail),
        code="HTTP_ERROR",
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Flatten pydantic errors into a readable list
    errors = [
        {
            "field": " → ".join(str(l) for l in err["loc"] if l != "body"),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    logger.warning(
        "Validation error | %s %s | %s fields",
        request.method,
        request.url.path,
        len(errors),
    )
    return _error_response(
        request,
        status_code=422,
        detail="Request validation failed",
        code="VALIDATION_ERROR",
        extra={"errors": errors},
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception | %s %s | %s",
        request.method,
        request.url.path,
        exc,
    )
    return _error_response(
        request,
        status_code=500,
        detail="An unexpected error occurred",
        code="INTERNAL_SERVER_ERROR",
    )


# ── Registration ──────────────────────────────────────────────────

def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)