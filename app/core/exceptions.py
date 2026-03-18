# app/core/exceptions.py


class AppBaseException(Exception):
    """Base class for all custom application exceptions."""

    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


# ------------------------------------------------------------------
# Auth exceptions
# ------------------------------------------------------------------

class UnauthorizedException(AppBaseException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(detail=detail, status_code=401)


class ForbiddenException(AppBaseException):
    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(detail=detail, status_code=403)


class InvalidTokenException(AppBaseException):
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(detail=detail, status_code=401)


class TokenBlacklistedException(AppBaseException):
    def __init__(self, detail: str = "Token has been revoked"):
        super().__init__(detail=detail, status_code=401)


# ------------------------------------------------------------------
# Tenant exceptions
# ------------------------------------------------------------------

class TenantNotFoundException(AppBaseException):
    def __init__(self, detail: str = "Tenant not found"):
        super().__init__(detail=detail, status_code=404)


class TenantInactiveException(AppBaseException):
    def __init__(self, detail: str = "Tenant account is inactive"):
        super().__init__(detail=detail, status_code=403)


class TenantHeaderMissingException(AppBaseException):
    def __init__(self, detail: str = "X-Tenant-ID header is required"):
        super().__init__(detail=detail, status_code=400)


# ------------------------------------------------------------------
# User exceptions
# ------------------------------------------------------------------

class UserAlreadyExistsException(AppBaseException):
    def __init__(self, detail: str = "User already exists"):
        super().__init__(detail=detail, status_code=400)


class UserNotFoundException(AppBaseException):
    def __init__(self, detail: str = "User not found"):
        super().__init__(detail=detail, status_code=404)


class InvalidCredentialsException(AppBaseException):
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(detail=detail, status_code=401)


# ------------------------------------------------------------------
# Resource exceptions
# ------------------------------------------------------------------

class NotFoundException(AppBaseException):
    def __init__(self, resource: str = "Resource"):
        super().__init__(detail=f"{resource} not found", status_code=404)


class ConflictException(AppBaseException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(detail=detail, status_code=409)


# ------------------------------------------------------------------
# Rate limit
# ------------------------------------------------------------------

class RateLimitExceededException(AppBaseException):
    def __init__(self, detail: str = "Too many requests. Please try again later."):
        super().__init__(detail=detail, status_code=429)


# ------------------------------------------------------------------
# Invitation exceptions
# ------------------------------------------------------------------

class InvitationNotFoundException(AppBaseException):
    def __init__(self, detail: str = "Invitation not found or invalid token"):
        super().__init__(detail=detail, status_code=404)


class InvitationExpiredException(AppBaseException):
    def __init__(self, detail: str = "Invitation has expired"):
        super().__init__(detail=detail, status_code=410)


class InvitationAlreadyAcceptedException(AppBaseException):
    def __init__(self, detail: str = "Invitation has already been accepted"):
        super().__init__(detail=detail, status_code=409)


class InvitationAlreadyExistsException(AppBaseException):
    def __init__(self, detail: str = "A pending invitation already exists for this email"):
        super().__init__(detail=detail, status_code=409)