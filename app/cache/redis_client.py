"""Redis client factory.

Treat Redis as a cache/hot-path store, not a second source of truth -- PostgreSQL stays
authoritative for anything durable. Session keys must carry a TTL.

TODO:
- get_redis() -> redis.asyncio.Redis, built from settings.redis_url
- helpers for table-state snapshot get/set, pub/sub publish/subscribe, and a
  distributed-lock helper (SET NX PX pattern) for the multi-instance case (Phase 5)
"""
