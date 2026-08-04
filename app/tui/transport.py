from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable


class TransportClosed(Exception):
    def __init__(self, code: int | None = None, reason: str = ""):
        self.code = code
        self.reason = reason
        super().__init__(f"transport closed (code={code}) {reason}".strip())


CLOSE_REASONS = {
    4401: "authentication rejected",
    4404: "table not found",
}


def close_reason(code: int | None) -> str:
    return CLOSE_REASONS.get(code or 0, "connection closed")


@runtime_checkable
class Transport(Protocol):
    async def connect(self, url: str) -> None: ...

    async def send(self, payload: dict[str, Any]) -> None: ...

    async def receive(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...


class WebsocketTransport:
    def __init__(self) -> None:
        self._ws: Any = None

    async def connect(self, url: str) -> None:
        from websockets.asyncio.client import connect as ws_connect

        try:
            self._ws = await ws_connect(url)
        except Exception as exc:
            code = getattr(getattr(exc, "rcvd", None), "code", None)
            raise TransportClosed(code, str(exc)) from exc

    async def send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise TransportClosed(None, "not connected")
        from websockets.exceptions import ConnectionClosed

        try:
            await self._ws.send(json.dumps(payload))
        except ConnectionClosed as exc:
            raise TransportClosed(_code_of(exc), "send after close") from exc

    async def receive(self) -> dict[str, Any]:
        if self._ws is None:
            raise TransportClosed(None, "not connected")
        from websockets.exceptions import ConnectionClosed

        try:
            raw = await self._ws.recv()
        except ConnectionClosed as exc:
            raise TransportClosed(_code_of(exc), "") from exc
        if isinstance(raw, bytes):
            raw = raw.decode()
        decoded: dict[str, Any] = json.loads(raw)
        return decoded

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None


def _code_of(exc: Exception) -> int | None:
    for attr in ("rcvd", "sent"):
        frame = getattr(exc, attr, None)
        if frame is not None and getattr(frame, "code", None) is not None:
            code: int = frame.code
            return code
    return None
