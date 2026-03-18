# app/schemas/user.py

from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    """Used in GET /members — includes role info."""
    id: int
    email: EmailStr
    role: str
    role_id: Optional[int]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RoleUpdateRequest(BaseModel):
    """Used in PATCH /members/{id}/role."""
    role_id: int


class ProfileResponse(BaseModel):
    """Used in GET /members/me — includes permissions list."""
    id: int
    email: EmailStr
    role: str
    role_id: Optional[int]
    is_active: bool
    tenant_id: int
    permissions: list[str]

    model_config = ConfigDict(from_attributes=True)


class PaginatedMembers(BaseModel):
    """Paginated wrapper for member list."""
    total: int
    page: int
    page_size: int
    items: list[MemberResponse]