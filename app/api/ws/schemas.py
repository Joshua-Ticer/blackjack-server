from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, Field

from app.engine.round import Seat

"""Pydantic envelopes for WebSocket client<->server events.

See docs/roadmap.md Part A Sec 5 for the full event catalogue.

TODO -- client -> server events:
- join_table, sit, place_bet, action (hit/stand/double/split/surrender), leave_table, ping
  Each client action should carry an `action_id: UUID` for idempotent dedup.

TODO -- server -> client events:
- table_state (full snapshot), state_delta, round_started, betting_open, betting_closed,
  player_turn (with deadline), round_result, error, pong
  Each table snapshot/delta should carry a monotonic `state_version` so stale actions
  from a reconnecting client can be rejected.

TODO: a discriminated union (Pydantic `type` field) to route incoming/outgoing messages.
"""


# Client -> Server
class JoinTable(BaseModel):
    type: Literal["join_table"] = "join_table"


class Sit(BaseModel):
    type: Literal["sit"] = "sit"


class PlaceBet(BaseModel):
    type: Literal["place_bet"] = "place_bet"
    amount: int
    action_id: UUID


class PlayerAction(BaseModel):
    type: Literal["action"] = "action"
    action: Literal["hit", "stand", "double", "split", "surrender"]
    action_id: UUID
    state_version: int | None = None


class LeaveTable(BaseModel):
    type: Literal["leave_table"] = "leave_table"


class Ping(BaseModel):
    type: Literal["ping"] = "ping"


ClientEvent = Annotated[
    JoinTable | Sit | PlaceBet | PlayerAction | LeaveTable | Ping,
    Field(discriminator="type"),
]


# Server -> Client
class SeatView(BaseModel):
    player_id: str
    hands: list[list[str]]  # e.g. [["7♣", "9♠"]] — one list per hand, for splits
    bets: list[int]
    outcomes: list[str | None] = []  # filled in only after settlement

    @classmethod
    def from_seat(cls, seat: Seat) -> "SeatView":
        return cls(
            player_id=seat.player_id,
            hands=[
                [f"{c.rank.value}{c.suit.value}" for c in hand.cards]
                for hand in seat.hands
            ],
            bets=seat.bets,
        )

    @classmethod
    def from_lobby_bet(cls, player_id: str, bet: int) -> "SeatView":
        return cls(player_id=player_id, hands=[], bets=[bet])


class TableStateMsg(BaseModel):
    type: Literal["table_state"] = "table_state"
    lobby_state: str  # "idle" | "betting_open" | "betting_closed" | "player_turns" | "dealer_turn" | "settlement"
    seats: list[SeatView]
    dealer_hand: list[
        str
    ]  # hole card omitted unless lobby_state is dealer_turn/settlement
    state_version: int


class StateDelta(BaseModel):
    type: Literal["state_delta"] = "state_delta"
    change: Literal["card_dealt", "action_applied", "bet_placed"]
    player_id: str | None = None  # None for a dealer card
    hand_index: int | None = None
    detail: dict  # small, change-specific payload, e.g. {"card": "9♠"}
    state_version: int


class BettingOpen(BaseModel):
    type: Literal["betting_open"] = "betting_open"
    deadline: datetime
    min_bet: int
    max_bet: int
    state_version: int


class BettingClosed(BaseModel):
    type: Literal["betting_closed"] = "betting_closed"
    state_version: int


class RoundStarted(BaseModel):
    type: Literal["round_started"] = "round_started"
    state_version: int


class PlayerTurn(BaseModel):
    type: Literal["player_turn"] = "player_turn"
    player_id: str
    hand_index: int
    legal_actions: list[str]
    deadline: datetime
    state_version: int


class SettlementItem(BaseModel):
    player_id: str
    hand_index: int
    outcome: str  # win/loss/push/blackjack/bust/surrender
    bet: int
    payout: int
    net: int
    balance_after: (
        int  # chip_balance post-settlement — saves the client a round trip to /users/me
    )


class RoundResultMsg(BaseModel):
    type: Literal["round_result"] = "round_result"
    results: list[SettlementItem]
    dealer_hand: list[str] = []
    state_version: int


class Pong(BaseModel):
    type: Literal["pong"] = "pong"


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    detail: str
    action_id: UUID | None = None


ServerEvent = Annotated[
    TableStateMsg
    | StateDelta
    | RoundStarted
    | BettingOpen
    | BettingClosed
    | PlayerTurn
    | RoundResultMsg
    | Pong
    | ErrorMsg,
    Field(discriminator="type"),
]
