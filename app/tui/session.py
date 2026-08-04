from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from app.tui.protocol import TableModel
from app.tui.transport import Transport, TransportClosed

UpdateHook = Callable[[dict[str, Any]], Awaitable[None]] | None
ClosedHook = Callable[[TransportClosed], Awaitable[None]] | None


class TableSession:
    def __init__(
        self,
        transport: Transport,
        me: str,
        on_update: UpdateHook = None,
        on_closed: ClosedHook = None,
    ):
        self.transport = transport
        self.model = TableModel(me=me)
        self.on_update = on_update
        self.on_closed = on_closed
        self.connected = False
        self.sent: list[dict[str, Any]] = []
        self._reader: asyncio.Task[None] | None = None

    async def connect(self, url: str) -> None:
        await self.transport.connect(url)
        self.connected = True
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            while True:
                message = await self.transport.receive()
                self.model.apply(message)
                if self.on_update is not None:
                    await self.on_update(message)
        except TransportClosed as closed:
            self.connected = False
            if self.on_closed is not None:
                await self.on_closed(closed)
        except asyncio.CancelledError:
            raise

    async def _send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)
        await self.transport.send(payload)

    async def join(self) -> None:
        await self._send({"type": "join_table"})

    async def sit(self) -> None:
        await self._send({"type": "sit"})

    async def place_bet(self, amount: int) -> None:
        await self._send(
            {"type": "place_bet", "amount": int(amount), "action_id": str(uuid4())}
        )

    async def act(self, action: str) -> None:
        await self._send(
            {
                "type": "action",
                "action": action,
                "action_id": str(uuid4()),
                "state_version": self.model.state_version,
            }
        )
        self.model.turn = None

    async def leave(self) -> None:
        await self._send({"type": "leave_table"})

    async def ping(self) -> None:
        await self._send({"type": "ping"})

    async def reconnect(self, url: str) -> None:
        await self.stop()
        await self.transport.connect(url)
        self.connected = True
        self._reader = asyncio.create_task(self._read_loop())
        await self.join()

    async def stop(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except (asyncio.CancelledError, Exception):
                pass
            self._reader = None
        self.connected = False
