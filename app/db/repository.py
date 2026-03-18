# app/db/repository.py
#
# Generic async repository. Subclass it for any model:
#
#   class ProjectRepository(TenantRepository[Project]):
#       model = Project
#
# Every method auto-filters by tenant_id so data never leaks
# across tenants.

from typing import Generic, TypeVar, Type, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import DeclarativeBase

ModelT = TypeVar("ModelT")


class TenantRepository(Generic[ModelT]):
    """
    Base CRUD repository scoped to a single tenant.

    All read/write operations automatically filter by tenant_id,
    so cross-tenant data leaks are structurally impossible.
    """

    model: Type[ModelT]

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # ── Internal helpers ──────────────────────────────────────────

    def _tenant_filter(self):
        return self.model.tenant_id == self.tenant_id

    def _base_query(self):
        return select(self.model).where(self._tenant_filter())

    # ── Create ────────────────────────────────────────────────────

    async def create(self, **kwargs) -> ModelT:
        """Create a new record scoped to the current tenant."""
        obj = self.model(tenant_id=self.tenant_id, **kwargs)
        self.db.add(obj)
        await self.db.flush()   # get id without committing
        await self.db.refresh(obj)
        return obj

    # ── Read ──────────────────────────────────────────────────────

    async def get(self, record_id: int) -> ModelT | None:
        """Fetch a single record by id, scoped to tenant."""
        result = await self.db.execute(
            self._base_query().where(self.model.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        # Cursor pagination
        cursor: int | None = None,       # last seen id
        limit: int = 20,
        # Filtering
        filters: dict[str, Any] | None = None,
        # Sorting
        sort_by: str = "id",
        sort_dir: str = "asc",
    ) -> tuple[list[ModelT], int, int | None]:
        """
        Return (items, total_count, next_cursor).

        next_cursor is the id of the last item returned,
        or None if this is the last page.
        """
        # ── Validate sort column ──────────────────────────────────
        sortable = {c.key for c in self.model.__table__.columns}
        if sort_by not in sortable:
            sort_by = "id"

        sort_col = getattr(self.model, sort_by)
        order_expr = sort_col.asc() if sort_dir == "asc" else sort_col.desc()

        # ── Build filter conditions ───────────────────────────────
        conditions = [self._tenant_filter()]

        if cursor is not None:
            if sort_dir == "asc":
                conditions.append(self.model.id > cursor)
            else:
                conditions.append(self.model.id < cursor)

        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field) and value is not None:
                    col = getattr(self.model, field)
                    if isinstance(value, str):
                        conditions.append(col.ilike(f"%{value}%"))
                    else:
                        conditions.append(col == value)

        # ── Total count (without cursor) ──────────────────────────
        count_conditions = [self._tenant_filter()]
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field) and value is not None:
                    col = getattr(self.model, field)
                    if isinstance(value, str):
                        count_conditions.append(col.ilike(f"%{value}%"))
                    else:
                        count_conditions.append(col == value)

        count_result = await self.db.execute(
            select(func.count(self.model.id)).where(and_(*count_conditions))
        )
        total = count_result.scalar()

        # ── Fetch items ───────────────────────────────────────────
        result = await self.db.execute(
            select(self.model)
            .where(and_(*conditions))
            .order_by(order_expr)
            .limit(limit + 1)   # fetch one extra to detect next page
        )
        items = list(result.scalars().all())

        # ── Compute next cursor ───────────────────────────────────
        next_cursor = None
        if len(items) > limit:
            items = items[:limit]
            next_cursor = items[-1].id

        return items, total, next_cursor

    # ── Update ────────────────────────────────────────────────────

    async def update(self, record_id: int, **kwargs) -> ModelT | None:
        """Update fields on an existing record. Returns None if not found."""
        obj = await self.get(record_id)
        if not obj:
            return None
        for field, value in kwargs.items():
            if hasattr(obj, field):
                setattr(obj, field, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    # ── Delete ────────────────────────────────────────────────────

    async def delete(self, record_id: int) -> bool:
        """Delete a record. Returns True if deleted, False if not found."""
        obj = await self.get(record_id)
        if not obj:
            return False
        await self.db.delete(obj)
        await self.db.flush()
        return True