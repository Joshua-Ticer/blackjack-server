import asyncio
import uuid

from fastapi import WebSocket
from redis.asyncio import Redis

from app.cache import redis_client as cache
from app.tables.table_actor import TableActor

LEASE_TTL_MS = 10_000
LEASE_RENEW_INTERVAL_S = 3


def _cancel_task(task: asyncio.Task) -> None:
    try:
        task.get_loop().call_soon_threadsafe(task.cancel)
    except RuntimeError:
        task.cancel()


class TableRelay:
    """Stands in for a TableActor on an instance that doesn't hold this table's
    Redis lease. Forwards locally-received client events to
    whichever instance owns the table, and relays that instance's broadcasts back
    out to this instance's own locally-connected sockets.
    """

    def __init__(self, table_id: str, redis: Redis):
        self.table_id = table_id
        self.redis = redis
        self.queue: asyncio.Queue = asyncio.Queue()
        self.connections: dict[WebSocket, str | None] = {}
        self._forward_task: asyncio.Task | None = None
        self._relay_task: asyncio.Task | None = None

    def register(self, ws: WebSocket):
        self.connections[ws] = None

    def unregister(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def handle_ping(self, ws: WebSocket):
        from app.api.ws.schemas import Pong

        await ws.send_json(Pong().model_dump(mode="json"))

    async def start(self) -> None:
        ready = asyncio.Event()
        self._relay_task = asyncio.create_task(self._relay_events(ready))
        self._forward_task = asyncio.create_task(self._forward_commands())
        await ready.wait()

    def stop(self) -> None:
        for task in (self._forward_task, self._relay_task):
            if task is not None:
                task.cancel()

    def pending_tasks(self) -> list[asyncio.Task]:
        return [t for t in (self._forward_task, self._relay_task) if t is not None]

    async def _forward_commands(self) -> None:
        channel = cache.COMMANDS_CHANNEL.format(table_id=self.table_id)
        while True:
            act, player_id, event, ws = await self.queue.get()
            if act == "join_table" and ws is not None:
                self.connections[ws] = player_id
            await cache.publish(
                self.redis,
                channel,
                {
                    "act": act,
                    "player_id": player_id,
                    "event": event.model_dump(mode="json"),
                },
            )

    async def _relay_events(self, ready: asyncio.Event) -> None:
        channel = cache.EVENTS_CHANNEL.format(table_id=self.table_id)
        async for message in cache.subscribe(self.redis, channel, ready=ready):
            target = message.get("target")
            payload = message.get("payload")
            dead = []
            for ws, pid in list(self.connections.items()):
                if target is None or target == pid:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
            for ws in dead:
                self.unregister(ws)


class TableManager:
    def __init__(self):
        self._actors: dict[str, TableActor] = {}
        self._relays: dict[str, TableRelay] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lease_tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.instance_id = uuid.uuid4().hex
        self.redis: Redis | None = None

    def set_redis(self, redis: Redis | None) -> None:
        self.redis = redis

    async def get_or_create(
        self, table_id, rules, seed=None
    ) -> TableActor | TableRelay:
        existing = self._actors.get(table_id) or self._relays.get(table_id)
        if existing is not None:
            return existing

        lock = self._locks.setdefault(table_id, asyncio.Lock())
        async with lock:
            existing = self._actors.get(table_id) or self._relays.get(table_id)
            if existing is not None:
                return existing

            if self.redis is None:
                return self._start_local_actor(table_id, rules, seed)

            owns_lease = await cache.renew_lease(
                self.redis, table_id, self.instance_id, LEASE_TTL_MS
            )
            if not owns_lease:
                owns_lease = await cache.acquire_table_lease(
                    self.redis, table_id, self.instance_id, LEASE_TTL_MS
                )
            if not owns_lease:
                relay = TableRelay(table_id, self.redis)
                self._relays[table_id] = relay
                await relay.start()
                return relay

            actor = self._start_local_actor(table_id, rules, seed, redis=self.redis)
            self._lease_tasks[table_id] = asyncio.create_task(
                self._renew_lease_loop(table_id)
            )

            snapshot = await cache.get_snapshot(self.redis, table_id)
            if snapshot is not None:
                actor.restore(snapshot)

            await actor.start_command_listener()
            return actor

    def _start_local_actor(
        self, table_id, rules, seed=None, redis: Redis | None = None
    ) -> TableActor:
        actor = TableActor(table_id, rules, seed=seed, redis=redis)
        self._actors[table_id] = actor
        self._tasks[table_id] = asyncio.create_task(actor.run())
        return actor

    async def _renew_lease_loop(self, table_id: str) -> None:
        assert self.redis is not None
        try:
            while True:
                await asyncio.sleep(LEASE_RENEW_INTERVAL_S)
                await cache.renew_lease(
                    self.redis, table_id, self.instance_id, LEASE_TTL_MS
                )
        except asyncio.CancelledError:
            pass

    def drop_local(self, table_id: str) -> None:
        task = self._tasks.pop(table_id, None)
        if task is not None:
            _cancel_task(task)

        actor = self._actors.pop(table_id, None)
        if actor is not None:
            for t in actor.pending_tasks():
                _cancel_task(t)

        lease_task = self._lease_tasks.pop(table_id, None)
        if lease_task is not None:
            _cancel_task(lease_task)

    def shutdown_all(self) -> None:
        tasks = list(self._tasks.values()) + list(self._lease_tasks.values())
        for actor in self._actors.values():
            tasks += actor.pending_tasks()
        for relay in self._relays.values():
            tasks += relay.pending_tasks()

        for task in tasks:
            _cancel_task(task)

        self._actors.clear()
        self._tasks.clear()
        self._relays.clear()
        self._lease_tasks.clear()

    def remove(self, table_id):
        task = self._tasks.pop(table_id, None)
        if task is not None:
            task.cancel()
        actor = self._actors.pop(table_id, None)
        if actor is not None:
            actor.stop()

        relay = self._relays.pop(table_id, None)
        if relay is not None:
            relay.stop()

        lease_task = self._lease_tasks.pop(table_id, None)
        if lease_task is not None:
            lease_task.cancel()
        if self.redis is not None:
            asyncio.create_task(
                cache.release_lease(self.redis, table_id, self.instance_id)
            )


table_manager = TableManager()
