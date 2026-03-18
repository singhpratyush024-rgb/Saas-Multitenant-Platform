# app/schemas/task.py

from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    status: str = "todo"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    tenant_id: int
    project_id: int
    assignee_id: Optional[int]
    title: str
    description: Optional[str]
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)