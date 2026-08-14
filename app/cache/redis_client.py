"""Redis client factory.

Treat Redis as a cache/hot-path store, not a second source of truth -- PostgreSQL stays
authoritative for anything durable. Session keys must carry a TTL.

TODO:
- get_redis() -> redis.asyncio.Redis, built from settings.redis_url
- helpers for table-state snapshot get/set, pub/sub publish/subscribe, and a
  distributed-lock helper (SET NX PX pattern) for the multi-instance case (Phase 5)
"""

import json
from collections.abc import AsyncIterator

import redis.exceptions
from redis.asyncio import Redis

from app.config import settings

SNAPSHOT_KEY = "table:{table_id}:snapshot"
EVENTS_CHANNEL = "table:{table_id}:events"
LEASE_KEY = "table:{table_id}:lease"

NETWORK_ERRORS = (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)

_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_RENEW_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

async def get_redis() -> Redis:
    try:
      client = Redis.from_url(settings.redis_url, decode_responses=True)
      await client.ping()
      return client
    except ValueError:
      print("Error: URL parsing failed")
      raise


async def set_snapshot(
    cache: Redis, table_id: str, payload: dict, ttl: int = 21600
) -> bool:
    try:
        key = SNAPSHOT_KEY.format(table_id=table_id)
        await cache.set(key, json.dumps(payload), ex=ttl)
        return True
    except NETWORK_ERRORS as e:
        print(f"snapshot write for {table_id} failed: {e}")
        return False


async def get_snapshot(cache: Redis, table_id: str) -> dict | None:
    payload = await cache.get(SNAPSHOT_KEY.format(table_id=table_id))
    return json.loads(payload) if payload is not None else None


async def publish(cache: Redis, channel: str, message: dict) -> bool:
    try:
        await cache.publish(channel, json.dumps(message))
        return True
    except NETWORK_ERRORS as e:
        print(f"publish to {channel} failed: {e}")
        return False

async def subscribe(cache: Redis, channel: str) -> AsyncIterator[dict]:
    pubsub = cache.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(channel)
    except NETWORK_ERRORS as e:
        print(f"could not subscribe to {channel}: {e}")
        return

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield json.loads(message["data"])
    except NETWORK_ERRORS as e:
        print(f"subscription to {channel} dropped: {e}")
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except NETWORK_ERRORS:
            pass

async def acquire_table_lease(
    cache: Redis, table_id: str, owner_id: str, ttl_ms: int = 10_000
) -> bool:
    key = LEASE_KEY.format(table_id=table_id)
    try:
        return await cache.set(key, owner_id, nx=True, px=ttl_ms) is True
    except NETWORK_ERRORS:
        return False


async def renew_lease(
    cache: Redis, table_id: str, owner_id: str, ttl_ms: int = 10_000
) -> bool:
    key = LEASE_KEY.format(table_id=table_id)
    try:
        return bool(await cache.eval(_RENEW_IF_OWNER, 1, key, owner_id, ttl_ms))
    except NETWORK_ERRORS:
        return False


async def release_lease(cache: Redis, table_id: str, owner_id: str) -> bool:
    key = LEASE_KEY.format(table_id=table_id)
    try:
        return bool(await cache.eval(_RELEASE_IF_OWNER, 1, key, owner_id))
    except NETWORK_ERRORS:
        return False
