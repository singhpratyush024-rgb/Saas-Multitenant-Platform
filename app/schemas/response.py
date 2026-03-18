# app/schemas/response.py
#
# Consistent response envelope used across all resource endpoints.
#
# Single item:
#   {"success": true, "data": {...}}
#
# List with cursor pagination:
#   {
#     "success": true,
#     "data": [...],
#     "meta": {
#       "total": 42,
#       "limit": 20,
#       "next_cursor": 35,
#       "has_more": true
#     }
#   }

from pydantic import BaseModel
from typing import Generic, TypeVar, Any

DataT = TypeVar("DataT")


class Meta(BaseModel):
    total: int
    limit: int
    next_cursor: int | None = None
    has_more: bool


class ResponseEnvelope(BaseModel, Generic[DataT]):
    success: bool = True
    data: DataT
    meta: Meta | None = None


def single(data: Any) -> dict:
    """Wrap a single item in the response envelope."""
    return {"success": True, "data": data}


def paginated(
    items: list,
    total: int,
    limit: int,
    next_cursor: int | None,
    serializer=None,
) -> dict:
    """
    Wrap a paginated list in the response envelope.
    Optionally pass a Pydantic model as serializer to convert ORM objects.
    """
    if serializer:
        serialized = [serializer.model_validate(item).model_dump() for item in items]
    else:
        serialized = items

    return {
        "success": True,
        "data": serialized,
        "meta": {
            "total": total,
            "limit": limit,
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        },
    }