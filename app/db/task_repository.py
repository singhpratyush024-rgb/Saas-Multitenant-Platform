# app/db/task_repository.py

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.db.repository import TenantRepository
from app.models.task import Task


class TaskRepository(TenantRepository[Task]):
    """
    Tenant-scoped repository for Tasks.
    Adds project_id scoping on top of tenant scoping.
    """
    model = Task

    def __init__(self, db: AsyncSession, tenant_id: int, project_id: int):
        super().__init__(db, tenant_id)
        self.project_id = project_id

    def _tenant_filter(self):
        return and_(
            self.model.tenant_id == self.tenant_id,
            self.model.project_id == self.project_id,
        )

    async def create(self, **kwargs) -> Task:
        obj = self.model(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            **kwargs,
        )
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj