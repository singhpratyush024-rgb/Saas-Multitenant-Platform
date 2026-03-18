# app/core/redis.py

import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TESTING = os.getenv("TESTING", "false").lower() == "true"

# Module-level client used in production
_redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def get_redis_client():
    """
    In tests: fresh client per call so each test's event loop
    gets its own connection.
    In production: reuse the module-level client.
    """
    if TESTING:
        return redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# Keep redis_client as a callable proxy so existing imports don't break
class _RedisProxy:
    """
    Proxies all attribute access to a fresh or shared redis client
    depending on the TESTING environment variable.
    This means existing code using `redis_client.get(...)` works unchanged.
    """
    def __getattr__(self, name):
        return getattr(get_redis_client(), name)


redis_client = _RedisProxy()