"""Offline demo: the real TUI driven by the real blackjack engine.

    python -m app.tui --demo

No server and no Postgres required. Hands, legal actions, dealer play and
settlement all come from app/engine, so outcomes are genuine.

Log in with any username/password, press enter on a table, then play.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.engine.card import Card, Suit
from app.engine.deck import Shoe
from app.engine.round import Round, Seat
from app.engine.rules import Action, TableRules
from app.tui.app import BlackjackApp
from app.tui.rest import RestClient

ME = "11111111-1111-1111-1111-111111111111"
BOT = "22222222-2222-2222-2222-222222222222"
TABLE_ID = "33333333-3333-3333-3333-333333333333"

TABLES: list[dict[str, Any]] = [
    {"id": TABLE_ID, "name": "High Roller", "min_bet": 25, "max_bet": 500, "status": "open"},
    {"id": "44444444-4444-4444-4444-444444444444", "name": "Low Stakes",
     "min_bet": 1, "max_bet": 50, "status": "open"},
]

BETTING_WINDOW = 30
TURN_TIMEOUT = 60
POST_ROUND_PAUSE = 3.0


def rules_for(table_id: str) -> TableRules:
    table = next((t for t in TABLES if t["id"] == table_id), TABLES[0])
    return TableRules(
        min_bet=int(table["min_bet"]),
        max_bet=int(table["max_bet"]),
        betting_window_seconds=BETTING_WINDOW,
        turn_timeout_seconds=TURN_TIMEOUT,
    )


def bot_bet_for(rules: TableRules) -> int:
    return max(rules.min_bet, min(10, rules.max_bet))


def deadline(seconds: float) -> str:
    return (datetime.now() + timedelta(seconds=seconds)).isoformat()


def cards_of(hand: Any) -> list[str]:
    return [str(c) for c in hand.cards]


class EngineTransport:
    """A single-table dealer backed by the real engine, speaking the WS protocol."""

    def __init__(self, force_pairs: bool = False) -> None:
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.shoe = Shoe()
        self.round: Round | None = None
        self.bet = 0
        self.balance = 1000
        self.version = 0
        self.force_pairs = force_pairs
        self.rules = rules_for(TABLE_ID)

    # -- transport interface ------------------------------------------------

    async def connect(self, url: str) -> None:
        # the ws url carries the table id, so the demo honours that table's limits
        table_id = url.split("/ws/tables/", 1)[-1].split("?", 1)[0]
        self.rules = rules_for(table_id)
        self.push(self.snapshot("idle"))

    async def close(self) -> None:
        pass

    async def receive(self) -> dict[str, Any]:
        return await self.outbox.get()

    async def send(self, payload: dict[str, Any]) -> None:
        kind = payload.get("type")
        if kind == "join_table":
            self.push(self.snapshot("idle"))
        elif kind == "sit":
            self.open_betting()
        elif kind == "place_bet":
            self.on_bet(int(payload["amount"]))
        elif kind == "action":
            self.on_action(payload["action"])
        elif kind == "ping":
            self.push({"type": "pong"})

    # -- plumbing -----------------------------------------------------------

    def next_version(self) -> int:
        self.version += 1
        return self.version

    def push(self, *messages: dict[str, Any]) -> None:
        for message in messages:
            self.outbox.put_nowait(message)

    def later(self, delay: float, *messages: dict[str, Any]) -> None:
        async def go() -> None:
            await asyncio.sleep(delay)
            self.push(*messages)

        asyncio.create_task(go())

    def later_call(self, delay: float, factory: Callable[[], dict[str, Any]]) -> None:
        """Build the message when the timer fires, so deadlines are not stale on arrival."""

        async def go() -> None:
            await asyncio.sleep(delay)
            self.push(factory())

        asyncio.create_task(go())

    def seat_view(self, seat: Seat) -> dict[str, Any]:
        return {
            "player_id": seat.player_id,
            "hands": [cards_of(h) for h in seat.hands],
            "bets": list(seat.bets),
            "outcomes": [],
        }

    def snapshot(self, lobby: str) -> dict[str, Any]:
        if self.round is None:
            seats = [
                {"player_id": ME, "hands": [], "bets": [self.bet], "outcomes": []},
                {"player_id": BOT, "hands": [], "bets": [bot_bet_for(self.rules)], "outcomes": []},
            ]
            dealer: list[str] = []
        else:
            seats = [self.seat_view(s) for s in self.round.seats]
            dealer = cards_of(self.round.dealer_hand)[:1]
        return {
            "type": "table_state",
            "lobby_state": lobby,
            "seats": seats,
            "dealer_hand": dealer,
            "state_version": self.next_version(),
        }

    # -- game flow ----------------------------------------------------------

    def open_betting(self) -> None:
        self.bet = 0
        self.round = None
        self.push({
            "type": "betting_open",
            "deadline": deadline(self.rules.betting_window_seconds),
            "min_bet": self.rules.min_bet,
            "max_bet": self.rules.max_bet,
            "state_version": self.next_version(),
        })

    def on_bet(self, amount: int) -> None:
        self.bet = amount
        self.push({
            "type": "state_delta",
            "change": "bet_placed",
            "player_id": ME,
            "hand_index": None,
            "detail": {"amount": amount},
            "state_version": self.next_version(),
        })
        self.later(1.2, *self.deal())

    def deal(self) -> list[dict[str, Any]]:
        if self.shoe.needs_shuffle(self.rules.penetration):
            self.shoe = Shoe()
        self.round = Round(
            self.shoe,
            self.rules,
            [
                Seat(player_id=ME, bets=[self.bet]),
                Seat(player_id=BOT, bets=[bot_bet_for(self.rules)]),
            ],
        )
        self.round.deal_initial()
        if self.force_pairs:
            for seat in self.round.seats:
                self.make_pair(seat)
        messages = [self.snapshot("player_turns")]
        messages.extend(self.advance())
        return messages

    def make_pair(self, seat: Seat) -> None:
        """Rewrite the second card to match the first so `split` is always legal."""
        hand = seat.hands[0]
        if len(hand.cards) < 2:
            return
        first = hand.cards[0]
        suit = next(s for s in Suit if s is not first.suit)
        hand.cards[1] = Card(rank=first.rank, suit=suit)

    def advance(self) -> list[dict[str, Any]]:
        assert self.round is not None
        for seat in self.round.seats:
            index = seat.active_hand_index
            if seat.is_hand_done(index):
                continue
            if seat.player_id == BOT:
                return self.play_bot()
            actions = self.round.legal_actions_for(ME)
            if not actions:
                continue
            return [{
                "type": "player_turn",
                "player_id": ME,
                "hand_index": index,
                "legal_actions": [a.value for a in actions],
                "deadline": deadline(self.rules.turn_timeout_seconds),
                "state_version": self.next_version(),
            }]
        return self.finish()

    def play_bot(self) -> list[dict[str, Any]]:
        assert self.round is not None
        messages: list[dict[str, Any]] = []
        seat = self.round._get_seat(BOT)
        while not seat.all_hands_done():
            index = seat.active_hand_index
            hand = seat.hands[index]
            action = Action.HIT if hand.total < 17 else Action.STAND
            self.round.player_action(BOT, action)
            messages.append({
                "type": "state_delta",
                "change": "action_applied",
                "player_id": BOT,
                "hand_index": index,
                "detail": {"action": action.value, "hand": cards_of(seat.hands[index])},
                "state_version": self.next_version(),
            })
        messages.extend(self.advance())
        return messages

    def on_action(self, action: str) -> None:
        assert self.round is not None
        seat = self.round._get_seat(ME)
        index = seat.active_hand_index
        self.round.player_action(ME, Action(action))
        self.push({
            "type": "state_delta",
            "change": "action_applied",
            "player_id": ME,
            "hand_index": index,
            "detail": {"action": action, "hand": cards_of(seat.hands[index])},
            "state_version": self.next_version(),
        })
        # an action_applied delta only carries one hand, so a split's second hand
        # is invisible until a full snapshot lands
        if len(seat.hands) > 1:
            self.push(self.snapshot("player_turns"))
        for message in self.advance():
            self.later(0.6, message)

    def finish(self) -> list[dict[str, Any]]:
        assert self.round is not None
        self.round.advance_to_dealer_turn()
        results = self.round.settle()

        mine = [r for r in results if r.player_id == ME]
        self.balance += sum(r.net for r in mine)

        result = {
            "type": "round_result",
            "results": [
                {
                    "player_id": r.player_id,
                    "hand_index": r.hand_index,
                    "outcome": r.outcome.value,
                    "bet": r.bet,
                    "payout": r.payout,
                    "net": r.net,
                    "balance_after": self.balance,
                }
                for r in results
            ],
            "dealer_hand": cards_of(self.round.dealer_hand),
            "state_version": self.next_version(),
        }
        # wait out the one-card-per-second reveal, then a beat to read the outcome
        pause = len(cards_of(self.round.dealer_hand)) + POST_ROUND_PAUSE
        self.later_call(pause, self.reopen)
        return [result]

    def reopen(self) -> dict[str, Any]:
        self.bet = 0
        self.round = None
        return {
            "type": "betting_open",
            "deadline": deadline(self.rules.betting_window_seconds),
            "min_bet": self.rules.min_bet,
            "max_bet": self.rules.max_bet,
            "state_version": self.next_version(),
        }


def fake_backend(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/auth/login":
        return httpx.Response(200, json={"access_token": "demo", "token_type": "bearer"})
    if path == "/auth/signup":
        return httpx.Response(400, json={"detail": "Username already taken"})
    if path == "/users/me":
        return httpx.Response(
            200,
            json={"id": ME, "username": "demo", "chip_balance": 1000, "is_admin": False},
        )
    if path == "/tables":
        return httpx.Response(200, json=TABLES)
    return httpx.Response(404, json={"detail": "not found"})


def build(force_pairs: bool = False) -> tuple[BlackjackApp, EngineTransport]:
    client = httpx.AsyncClient(
        base_url="http://demo", transport=httpx.MockTransport(fake_backend)
    )
    rest = RestClient("http://demo", client=client)
    transport = EngineTransport(force_pairs=force_pairs)
    return BlackjackApp(rest=rest, transport_factory=lambda: transport), transport

