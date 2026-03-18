# app/core/exception_handlers.py

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppBaseException

logger = logging.getLogger(__name__)


def _error_response(status_code: int, detail, extra: dict = None) -> JSONResponse:
    """Consistent JSON error envelope used by every handler."""
    content = {"success": False, "detail": detail}
    if extra:
        content.update(extra)
    return JSONResponse(status_code=status_code, content=content)


# ------------------------------------------------------------------
# 1. Custom app exceptions  (AppBaseException and subclasses)
# ------------------------------------------------------------------
async def app_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    logger.warning(
        "App exception | %s %s | %s %s",
        request.method, request.url.path, exc.status_code, exc.detail
    )
    return _error_response(exc.status_code, exc.detail)


# ------------------------------------------------------------------
# 2. FastAPI / Starlette HTTP exceptions  (HTTPException)
# ------------------------------------------------------------------
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "HTTP exception | %s %s | %s %s",
        request.method, request.url.path, exc.status_code, exc.detail
    )
    return _error_response(exc.status_code, exc.detail)


# ------------------------------------------------------------------
# 3. Pydantic validation errors  (422 Unprocessable Entity)
# ------------------------------------------------------------------
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Flatten Pydantic errors into a clean list
    errors = [
        {
            "field": " → ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]

    logger.warning(
        "Validation error | %s %s | %s",
        request.method, request.url.path, errors
    )

    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Request validation failed",
        extra={"errors": errors},
    )


# ------------------------------------------------------------------
# 4. Catch-all — unhandled exceptions  (500)
# ------------------------------------------------------------------
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception | %s %s",
        request.method, request.url.path
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please try again later.",
    )


# ------------------------------------------------------------------
# Registration helper — call this in main.py
# ------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppBaseException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)