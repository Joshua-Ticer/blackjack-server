import asyncio
import os

import pytest
from redis.asyncio import Redis

from app.cache.redis_client import (
    EVENTS_CHANNEL,
    LEASE_KEY,
    NETWORK_ERRORS,
    SNAPSHOT_KEY,
    acquire_table_lease,
    get_snapshot,
    publish,
    release_lease,
    renew_lease,
    set_snapshot,
    subscribe,
)

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
DEAD_REDIS_URL = "redis://localhost:6399/0"


@pytest.fixture
async def cache():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def dead_cache():
    return Redis.from_url(
        DEAD_REDIS_URL, decode_responses=True, socket_connect_timeout=0.25
    )


async def collect_one(cache, channel, received):
    async for message in subscribe(cache, channel):
        received.append(message)
        return


async def test_snapshot_survives_a_roundtrip(cache):
    payload = {"version": 3, "seats": {"p1": 25}, "round": None}
    assert await set_snapshot(cache, "t1", payload, ttl=60)

    assert await get_snapshot(cache, "t1") == payload


async def test_missing_snapshot_reads_as_none(cache):
    assert await get_snapshot(cache, "never-seen") is None


async def test_snapshot_carries_its_ttl(cache):
    await set_snapshot(cache, "t1", {"version": 1}, ttl=60)

    ttl = await cache.ttl(SNAPSHOT_KEY.format(table_id="t1"))
    assert 0 < ttl <= 60


async def test_published_event_reaches_a_subscriber(cache):
    channel = EVENTS_CHANNEL.format(table_id="t1")
    received = []
    consumer = asyncio.create_task(collect_one(cache, channel, received))
    await asyncio.sleep(0.15)

    assert await publish(cache, channel, {"type": "pong"})
    await asyncio.wait_for(consumer, timeout=2)

    assert received == [{"type": "pong"}]


async def test_subscriber_ignores_other_tables(cache):
    mine = EVENTS_CHANNEL.format(table_id="t1")
    theirs = EVENTS_CHANNEL.format(table_id="t2")
    received = []
    consumer = asyncio.create_task(collect_one(cache, mine, received))
    await asyncio.sleep(0.15)

    await publish(cache, theirs, {"type": "not-for-me"})
    await publish(cache, mine, {"type": "pong"})
    await asyncio.wait_for(consumer, timeout=2)

    assert received == [{"type": "pong"}]


async def test_subscription_is_torn_down_when_the_consumer_stops(cache):
    channel = EVENTS_CHANNEL.format(table_id="t1")
    received = []
    consumer = asyncio.create_task(collect_one(cache, channel, received))
    await asyncio.sleep(0.15)
    assert channel in await cache.pubsub_channels()

    await publish(cache, channel, {"type": "pong"})
    await asyncio.wait_for(consumer, timeout=2)
    await asyncio.sleep(0.1)

    assert channel not in await cache.pubsub_channels()


async def test_a_second_instance_cannot_take_a_held_lease(cache):
    assert await acquire_table_lease(cache, "t1", "instance-a", 5_000)

    assert not await acquire_table_lease(cache, "t1", "instance-b", 5_000)


async def test_a_non_owner_cannot_release_or_renew(cache):
    await acquire_table_lease(cache, "t1", "instance-a", 5_000)

    assert not await release_lease(cache, "t1", "instance-b")
    assert not await renew_lease(cache, "t1", "instance-b", 5_000)
    assert not await acquire_table_lease(cache, "t1", "instance-b", 5_000)
    assert await cache.get(LEASE_KEY.format(table_id="t1")) == "instance-a"


async def test_release_hands_the_table_to_the_next_instance(cache):
    await acquire_table_lease(cache, "t1", "instance-a", 5_000)

    assert await release_lease(cache, "t1", "instance-a")
    assert await acquire_table_lease(cache, "t1", "instance-b", 5_000)


async def test_lease_expires_so_a_crashed_owner_frees_the_table(cache):
    assert await acquire_table_lease(cache, "t1", "instance-a", 200)
    await asyncio.sleep(0.3)

    assert await acquire_table_lease(cache, "t1", "instance-b", 5_000)


async def test_renewing_keeps_the_lease_past_its_original_ttl(cache):
    await acquire_table_lease(cache, "t1", "instance-a", 300)
    await asyncio.sleep(0.15)

    assert await renew_lease(cache, "t1", "instance-a", 5_000)
    await asyncio.sleep(0.25)

    assert not await acquire_table_lease(cache, "t1", "instance-b", 5_000)


async def test_an_expired_owner_cannot_renew_over_the_new_owner(cache):
    await acquire_table_lease(cache, "t1", "instance-a", 200)
    await asyncio.sleep(0.3)
    await acquire_table_lease(cache, "t1", "instance-b", 5_000)

    assert not await renew_lease(cache, "t1", "instance-a", 5_000)
    assert await cache.get(LEASE_KEY.format(table_id="t1")) == "instance-b"


async def test_writes_degrade_instead_of_crashing_when_redis_is_down(dead_cache):
    assert await set_snapshot(dead_cache, "t1", {"version": 1}) is False
    assert await publish(dead_cache, "table:t1:events", {"type": "pong"}) is False


async def test_leases_are_refused_when_redis_is_down(dead_cache):
    assert not await acquire_table_lease(dead_cache, "t1", "instance-a")
    assert not await renew_lease(dead_cache, "t1", "instance-a")
    assert not await release_lease(dead_cache, "t1", "instance-a")


async def test_subscribe_yields_nothing_when_redis_is_down(dead_cache):
    received = [message async for message in subscribe(dead_cache, "table:t1:events")]

    assert received == []


async def test_an_outage_is_distinguishable_from_a_cache_miss(dead_cache):
    with pytest.raises(NETWORK_ERRORS):
        await get_snapshot(dead_cache, "t1")
