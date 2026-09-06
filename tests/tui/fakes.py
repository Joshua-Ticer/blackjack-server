from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from app.tui.rest import RestClient
from app.tui.transport import TransportClosed

ME = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
TABLE_ID = "33333333-3333-3333-3333-333333333333"


def deadline_in(seconds: float) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).isoformat()


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.connected = False
        self.connect_error: Exception | None = None
        self.urls: list[str] = []
        self.connect_count = 0

    async def connect(self, url: str) -> None:
        self.connect_count += 1
        if self.connect_error is not None:
            raise self.connect_error
        self.urls.append(url)
        self.connected = True

    async def send(self, payload: dict[str, Any]) -> None:
        if not self.connected:
            raise TransportClosed(None, "not connected")
        self.sent.append(payload)

    async def receive(self) -> dict[str, Any]:
        item = await self.incoming.get()
        if isinstance(item, TransportClosed):
            self.connected = False
            raise item
        message: dict[str, Any] = item
        return message

    async def close(self) -> None:
        self.connected = False

    def feed(self, *messages: dict[str, Any]) -> None:
        for message in messages:
            self.incoming.put_nowait(message)

    def drop(self, code: int | None = None) -> None:
        self.incoming.put_nowait(TransportClosed(code))

    def sent_of(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.sent if m.get("type") == kind]


# --- server -> client message builders -------------------------------------


def table_state(
    lobby_state: str = "idle",
    seats: list[dict[str, Any]] | None = None,
    dealer_hand: list[str] | None = None,
    state_version: int = 1,
) -> dict[str, Any]:
    return {
        "type": "table_state",
        "lobby_state": lobby_state,
        "seats": seats if seats is not None else [],
        "dealer_hand": dealer_hand or [],
        "state_version": state_version,
    }


def seat(
    player_id: str,
    hands: list[list[str]] | None = None,
    bets: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "hands": hands if hands is not None else [],
        "bets": bets if bets is not None else [0],
        "outcomes": [],
    }


def betting_open(
    seconds: float = 15, min_bet: int = 5, max_bet: int = 500, state_version: int = 2
) -> dict[str, Any]:
    return {
        "type": "betting_open",
        "deadline": deadline_in(seconds),
        "min_bet": min_bet,
        "max_bet": max_bet,
        "state_version": state_version,
    }


def player_turn(
    player_id: str = ME,
    hand_index: int = 0,
    legal_actions: list[str] | None = None,
    seconds: float = 30,
    state_version: int = 5,
) -> dict[str, Any]:
    return {
        "type": "player_turn",
        "player_id": player_id,
        "hand_index": hand_index,
        "legal_actions": (
            legal_actions if legal_actions is not None else ["hit", "stand"]
        ),
        "deadline": deadline_in(seconds),
        "state_version": state_version,
    }


def bet_placed(
    player_id: str = ME, amount: int = 25, state_version: int = 3
) -> dict[str, Any]:
    return {
        "type": "state_delta",
        "change": "bet_placed",
        "player_id": player_id,
        "hand_index": None,
        "detail": {"amount": amount},
        "state_version": state_version,
    }


def action_applied(
    player_id: str = ME,
    hand_index: int = 0,
    action: str = "hit",
    hand: list[str] | None = None,
    state_version: int = 6,
) -> dict[str, Any]:
    return {
        "type": "state_delta",
        "change": "action_applied",
        "player_id": player_id,
        "hand_index": hand_index,
        "detail": {"action": action, "hand": hand or ["7C", "9S", "5D"]},
        "state_version": state_version,
    }


def round_result(
    player_id: str = ME,
    outcome: str = "win",
    bet: int = 25,
    payout: int = 50,
    net: int = 25,
    balance_after: int = 1025,
    dealer_hand: list[str] | None = None,
    state_version: int = 8,
) -> dict[str, Any]:
    return {
        "type": "round_result",
        "results": [
            {
                "player_id": player_id,
                "hand_index": 0,
                "outcome": outcome,
                "bet": bet,
                "payout": payout,
                "net": net,
                "balance_after": balance_after,
            }
        ],
        "dealer_hand": dealer_hand or ["AC", "KC"],
        "state_version": state_version,
    }


def error(detail: str = "betting is closed") -> dict[str, Any]:
    return {"type": "error", "detail": detail, "action_id": None}


# --- fake REST backend ------------------------------------------------------


class FakeBackend:
    def __init__(self) -> None:
        self.users: dict[str, str] = {}
        self.chip_balance = 1000
        self.tables: list[dict[str, Any]] = [
            {
                "id": TABLE_ID,
                "name": "High Roller",
                "min_bet": 5,
                "max_bet": 500,
                "status": "open",
            }
        ]
        self.username = "player"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/auth/signup":
            import json as _json

            body = _json.loads(request.content)
            if body["username"] in self.users:
                return httpx.Response(400, json={"detail": "Username already taken"})
            self.users[body["username"]] = body["password"]
            return httpx.Response(200, json=self._user(body["username"]))

        if path == "/auth/login":
            form = dict(httpx.QueryParams(request.content.decode()))
            username = form.get("username", "")
            if self.users and self.users.get(username) != form.get("password"):
                return httpx.Response(
                    401, json={"detail": "Incorrect username or password"}
                )
            self.username = username
            return httpx.Response(
                200, json={"access_token": "test-token", "token_type": "bearer"}
            )

        if path == "/users/me":
            if request.headers.get("Authorization") != "Bearer test-token":
                return httpx.Response(401, json={"detail": "Not authenticated"})
            return httpx.Response(200, json=self._user(self.username))

        if path == "/tables":
            return httpx.Response(200, json=self.tables)

        return httpx.Response(404, json={"detail": "not found"})

    def _user(self, username: str) -> dict[str, Any]:
        return {
            "id": ME,
            "username": username,
            "chip_balance": self.chip_balance,
            "is_admin": False,
        }


def fake_rest(backend: FakeBackend | None = None) -> tuple[RestClient, FakeBackend]:
    backend = backend or FakeBackend()
    client = httpx.AsyncClient(
        base_url="http://testserver", transport=httpx.MockTransport(backend.handler)
    )
    return RestClient("http://testserver", client=client), backend


def new_action_id() -> str:
    return str(uuid4())
