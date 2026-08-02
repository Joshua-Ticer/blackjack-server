"""Pure-Python blackjack rules engine.

No FastAPI, DB, or Redis imports allowed in this package. Everything here must be
deterministic given a seed and testable with zero I/O -- see docs/roadmap.md Phase 1.
"""

from .card import Card, Rank, Suit
from .deck import Shoe
from .hand import Hand
from .rules import Action, TableRules, legal_actions
from .dealer import play_dealer_hand
from .state_machine import (
    TRANSITIONS,
    InvalidTransition,
    StateMachine,
    TableEvent,
    TableState,
)
from .settlement import Outcome, SettlementResult, settle_hand
from .round import (
    IllegalActionError,
    InvalidBetError,
    Round,
    RoundError,
    Seat,
    SeatNotFoundError,
)

__all__ = [
    "Card",
    "Rank",
    "Suit",
    "Shoe",
    "Hand",
    "Action",
    "TableRules",
    "legal_actions",
    "play_dealer_hand",
    "TRANSITIONS",
    "InvalidTransition",
    "StateMachine",
    "TableEvent",
    "TableState",
    "Outcome",
    "SettlementResult",
    "settle_hand",
    "IllegalActionError",
    "InvalidBetError",
    "Round",
    "RoundError",
    "Seat",
    "SeatNotFoundError",
]
