# app/db/cache.py
#
# Per-tenant Redis cache for GET endpoints.
# Usage:
#
#   cache = TenantCache(tenant_id=1, prefix="projects")
#
#   # Try cache first
#   data = await cache.get("list:cursor=0:limit=20")
#   if data is None:
#       data = fetch_from_db()
#       await cache.set("list:cursor=0:limit=20", data)
#
#   # Invalidate on write
#   await cache.invalidate()          # clears ALL keys for this tenant+prefix
#   await cache.invalidate("detail:5") # clears one specific key

import json
import logging
from typing import Any

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300   # 5 minutes


class TenantCache:
    """
    Namespaced Redis cache scoped to a tenant and resource type.

    Key pattern:  cache:{prefix}:tenant:{tenant_id}:{key}
    Index key:    cache:{prefix}:tenant:{tenant_id}:__keys__

    The index key tracks all cache keys for this tenant+prefix
    so we can invalidate them all in one sweep on any write.
    """

    def __init__(self, tenant_id: int, prefix: str, ttl: int = DEFAULT_TTL):
        self.tenant_id = tenant_id
        self.prefix = prefix
        self.ttl = ttl

    def _key(self, key: str) -> str:
        return f"cache:{self.prefix}:tenant:{self.tenant_id}:{key}"

    def _index_key(self) -> str:
        return f"cache:{self.prefix}:tenant:{self.tenant_id}:__keys__"

    async def get(self, key: str) -> Any | None:
        """Return cached value or None on miss/error."""
        try:
            raw = await redis_client.get(self._key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning("Cache get failed for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any) -> None:
        """Store value in cache and register key in the index."""
        try:
            full_key = self._key(key)
            await redis_client.setex(full_key, self.ttl, json.dumps(value))
            # Track this key in the index for bulk invalidation
            await redis_client.sadd(self._index_key(), full_key)
            await redis_client.expire(self._index_key(), self.ttl)
        except Exception as e:
            logger.warning("Cache set failed for key %s: %s", key, e)

    async def invalidate(self, key: str | None = None) -> None:
        """
        Invalidate cache.
        - key=None  → invalidate ALL keys for this tenant+prefix
        - key=str   → invalidate one specific key
        """
        try:
            if key is not None:
                await redis_client.delete(self._key(key))
                await redis_client.srem(self._index_key(), self._key(key))
            else:
                # Fetch all tracked keys and delete them
                index_key = self._index_key()
                keys = await redis_client.smembers(index_key)
                if keys:
                    await redis_client.delete(*keys)
                await redis_client.delete(index_key)
        except Exception as e:
            logger.warning("Cache invalidation failed: %s", e)