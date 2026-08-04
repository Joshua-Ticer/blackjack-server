from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

LOBBY_IDLE = "idle"
LOBBY_BETTING_OPEN = "betting_open"
LOBBY_BETTING_CLOSED = "betting_closed"
LOBBY_PLAYER_TURNS = "player_turns"
LOBBY_DEALER_TURN = "dealer_turn"
LOBBY_SETTLEMENT = "settlement"

REVEALED_STATES = (LOBBY_DEALER_TURN, LOBBY_SETTLEMENT)


def parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


@dataclass
class Betting:
    deadline: datetime | None
    min_bet: int
    max_bet: int


@dataclass
class Turn:
    hand_index: int
    legal_actions: tuple[str, ...]
    deadline: datetime | None
    state_version: int


@dataclass
class SeatState:
    player_id: str
    hands: list[list[str]] = field(default_factory=list)
    bets: list[int] = field(default_factory=list)


@dataclass
class ResultLine:
    player_id: str
    hand_index: int
    outcome: str
    bet: int
    payout: int
    net: int
    balance_after: int


class TableModel:
    def __init__(self, me: str):
        self.me = me
        self.lobby_state: str = LOBBY_IDLE
        self.seats: list[SeatState] = []
        self.dealer_hand: list[str] = []
        self.dealer_revealed: bool = False
        self.dealer_visible: int = 0
        self.state_version: int = 0
        self.betting: Betting | None = None
        self.turn: Turn | None = None
        self.results: list[ResultLine] | None = None
        self.error: str | None = None
        self.my_bet: int = 0
        self.seated: bool = False

    @property
    def my_seat(self) -> SeatState | None:
        for seat in self.seats:
            if seat.player_id == self.me:
                return seat
        return None

    @property
    def is_my_turn(self) -> bool:
        return self.turn is not None

    def legal_actions(self) -> tuple[str, ...]:
        return self.turn.legal_actions if self.turn else ()

    def can(self, action: str) -> bool:
        return action in self.legal_actions()

    def active_deadline(self) -> datetime | None:
        if self.turn is not None:
            return self.turn.deadline
        if self.betting is not None and self.lobby_state == LOBBY_BETTING_OPEN:
            return self.betting.deadline
        return None

    def betting_is_open(self) -> bool:
        return self.lobby_state == LOBBY_BETTING_OPEN

    def visible_dealer_cards(self) -> list[str]:
        return self.dealer_hand[: self.dealer_visible]

    def dealer_face_down(self) -> int:
        if self.dealer_revealed:
            return 0
        return 1 if self.dealer_visible < 2 else 0

    def reveal_pending(self) -> bool:
        return self.results is not None and not self.dealer_revealed

    def advance_dealer_reveal(self) -> bool:
        if self.dealer_revealed:
            return True
        self.dealer_visible = min(self.dealer_visible + 1, len(self.dealer_hand))
        if self.dealer_visible >= len(self.dealer_hand):
            self.dealer_revealed = True
        return self.dealer_revealed

    @property
    def settlement_visible(self) -> bool:
        return self.results is not None and self.dealer_revealed

    def visible_results(self) -> list[ResultLine]:
        return self.my_results() if self.settlement_visible else []

    def _seat_for(self, player_id: str) -> SeatState:
        for seat in self.seats:
            if seat.player_id == player_id:
                return seat
        seat = SeatState(player_id=player_id)
        self.seats.append(seat)
        return seat

    def _clear_last_round(self) -> None:
        self.results = None
        self.dealer_revealed = False

    def apply(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        version = msg.get("state_version")
        if isinstance(version, int) and version > self.state_version:
            self.state_version = version

        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(msg)

    def _on_table_state(self, msg: dict[str, Any]) -> None:
        previous = self.lobby_state
        self.lobby_state = msg["lobby_state"]
        self.seats = [
            SeatState(
                player_id=s["player_id"],
                hands=[list(h) for h in s.get("hands", [])],
                bets=list(s.get("bets", [])),
            )
            for s in msg.get("seats", [])
        ]
        self.dealer_hand = list(msg.get("dealer_hand", []))
        self.dealer_revealed = self.lobby_state in REVEALED_STATES
        self.dealer_visible = len(self.dealer_hand)
        self.seated = self.my_seat is not None

        mine = self.my_seat
        if mine is not None and mine.bets:
            self.my_bet = mine.bets[0]

        if self.lobby_state == LOBBY_PLAYER_TURNS and previous != LOBBY_PLAYER_TURNS:
            self._clear_last_round()
        if self.lobby_state != LOBBY_PLAYER_TURNS:
            self.turn = None

    def _on_betting_open(self, msg: dict[str, Any]) -> None:
        self.turn = None
        self.my_bet = 0
        self.lobby_state = LOBBY_BETTING_OPEN
        self.betting = Betting(
            deadline=parse_deadline(msg.get("deadline")),
            min_bet=msg["min_bet"],
            max_bet=msg["max_bet"],
        )

    def _on_player_turn(self, msg: dict[str, Any]) -> None:
        if msg.get("player_id") != self.me:
            return
        self.lobby_state = LOBBY_PLAYER_TURNS
        if not msg.get("legal_actions"):
            self.turn = None
            return
        self.turn = Turn(
            hand_index=msg["hand_index"],
            legal_actions=tuple(msg.get("legal_actions", [])),
            deadline=parse_deadline(msg.get("deadline")),
            state_version=msg["state_version"],
        )

    def _on_state_delta(self, msg: dict[str, Any]) -> None:
        change = msg.get("change")
        player_id = msg.get("player_id")
        detail = msg.get("detail") or {}

        if change == "bet_placed" and player_id is not None:
            seat = self._seat_for(player_id)
            amount = int(detail.get("amount", 0))
            if seat.bets:
                seat.bets[0] = amount
            else:
                seat.bets = [amount]
            if player_id == self.me:
                self.my_bet = amount
                self.error = None

        elif change == "action_applied" and player_id is not None:
            seat = self._seat_for(player_id)
            index = msg.get("hand_index") or 0
            hand = list(detail.get("hand", []))
            while len(seat.hands) <= index:
                seat.hands.append([])
            seat.hands[index] = hand
            if player_id == self.me:
                self.turn = None

    def _on_round_result(self, msg: dict[str, Any]) -> None:
        if not msg.get("results"):
            return
        self.results = [
            ResultLine(
                player_id=r["player_id"],
                hand_index=r["hand_index"],
                outcome=r["outcome"],
                bet=r["bet"],
                payout=r["payout"],
                net=r["net"],
                balance_after=r["balance_after"],
            )
            for r in msg.get("results", [])
        ]
        self.dealer_hand = list(msg.get("dealer_hand", []))
        self.dealer_visible = min(self.dealer_visible, len(self.dealer_hand))
        self.dealer_revealed = self.dealer_visible >= len(self.dealer_hand)
        self.turn = None
        self.lobby_state = LOBBY_SETTLEMENT

    def _on_error(self, msg: dict[str, Any]) -> None:
        self.error = msg.get("detail", "unknown error")

    def my_results(self) -> list[ResultLine]:
        return [r for r in (self.results or []) if r.player_id == self.me]
