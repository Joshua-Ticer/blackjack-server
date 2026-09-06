import asyncio
from uuid import uuid4

from app.api.ws.schemas import JoinTable, Sit
from app.cache import redis_client as cache
from app.engine.rules import TableRules
from app.tables.table_manager import TableActor, TableManager, TableRelay


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


async def test_second_instance_gets_a_relay_not_ownership():
    table_id = str(uuid4())
    rules = TableRules(min_bet=5, max_bet=500)
    redis = cache.get_shared_client()

    mgr_a = TableManager()
    mgr_a.set_redis(redis)
    mgr_b = TableManager()
    mgr_b.set_redis(redis)

    try:
        owner = await mgr_a.get_or_create(table_id, rules, seed=1)
        relay = await mgr_b.get_or_create(table_id, rules)

        assert isinstance(owner, TableActor)
        assert isinstance(relay, TableRelay)
    finally:
        mgr_a.shutdown_all()
        mgr_b.shutdown_all()


async def test_relay_forwards_join_and_relays_the_snapshot_back():
    table_id = str(uuid4())
    rules = TableRules(min_bet=5, max_bet=500)
    redis = cache.get_shared_client()

    mgr_a = TableManager()
    mgr_a.set_redis(redis)
    mgr_b = TableManager()
    mgr_b.set_redis(redis)

    try:
        await mgr_a.get_or_create(table_id, rules, seed=1)
        relay = await mgr_b.get_or_create(table_id, rules)

        ws = FakeWebSocket()
        relay.register(ws)
        await relay.queue.put(("join_table", "p1", JoinTable(), ws))

        for _ in range(20):
            if any(m.get("type") == "table_state" for m in ws.sent):
                break
            await asyncio.sleep(0.05)

        assert any(m["type"] == "table_state" for m in ws.sent)
    finally:
        mgr_a.shutdown_all()
        mgr_b.shutdown_all()


async def test_action_sent_to_a_relay_reaches_the_owning_actor():
    table_id = str(uuid4())
    rules = TableRules(min_bet=5, max_bet=500)
    redis = cache.get_shared_client()

    mgr_a = TableManager()
    mgr_a.set_redis(redis)
    mgr_b = TableManager()
    mgr_b.set_redis(redis)

    try:
        owner = await mgr_a.get_or_create(table_id, rules, seed=1)
        relay = await mgr_b.get_or_create(table_id, rules)

        ws = FakeWebSocket()
        relay.register(ws)
        await relay.queue.put(("join_table", "p1", JoinTable(), ws))
        await relay.queue.put(("sit", "p1", Sit(), ws))

        for _ in range(20):
            if "p1" in owner._seats:
                break
            await asyncio.sleep(0.05)

        assert "p1" in owner._seats
    finally:
        mgr_a.shutdown_all()
        mgr_b.shutdown_all()


async def test_owner_broadcast_reaches_relay_connected_players():
    table_id = str(uuid4())
    rules = TableRules(min_bet=5, max_bet=500, betting_window_seconds=60)
    redis = cache.get_shared_client()

    mgr_a = TableManager()
    mgr_a.set_redis(redis)
    mgr_b = TableManager()
    mgr_b.set_redis(redis)

    try:
        owner = await mgr_a.get_or_create(table_id, rules, seed=1)
        relay = await mgr_b.get_or_create(table_id, rules)

        ws = FakeWebSocket()
        relay.register(ws)
        await relay.queue.put(("join_table", "p1", JoinTable(), ws))
        await relay.queue.put(("sit", "p1", Sit(), ws))

        for _ in range(30):
            if any(m.get("type") == "betting_open" for m in ws.sent):
                break
            await asyncio.sleep(0.05)

        assert any(m["type"] == "betting_open" for m in ws.sent)
        assert owner.sm.state.name == "BETTING_OPEN"
    finally:
        mgr_a.shutdown_all()
        mgr_b.shutdown_all()
