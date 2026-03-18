# app/schemas/invitation.py

from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional


class InvitationCreate(BaseModel):
    email: EmailStr
    role_id: int


class InvitationResponse(BaseModel):
    id: int
    email: EmailStr
    tenant_id: int
    role_id: Optional[int]
    expires_at: datetime
    accepted_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class InvitationAccept(BaseModel):
    token: str
    password: str