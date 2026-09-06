"""Explicit finite-state machine for table state and per-hand state.

Model states as enum.Enum and transitions as a (state, event) -> state mapping, not
nested if/else or boolean flags -- see docs/roadmap.md Part A Sec 6.

TODO:
- TableState enum: IDLE, BETTING_OPEN, BETTING_CLOSED, DEALING, PLAYER_TURNS,
  DEALER_TURN, SETTLEMENT
- HandState enum: ACTIVE, STANDING, BUSTED, BLACKJACK, DOUBLED, SURRENDERED
- TRANSITIONS: dict[tuple[State, Event], State]
- can_transition(state, event) -> bool
- transition(state, event) -> State  (raises on illegal transition)
"""

from enum import Enum, auto


class TableState(Enum):
    IDLE = auto()
    BETTING_OPEN = auto()
    BETTING_CLOSED = auto()
    DEALING = auto()
    PLAYER_TURNS = auto()
    DEALER_TURN = auto()
    SETTLEMENT = auto()


class TableEvent(Enum):
    PLAYERS_SEATED = auto()
    BETS_LOCKED = auto()
    START_DEAL = auto()
    DEAL_COMPLETE = auto()
    ALL_PLAYERS_DONE = auto()
    DEALER_DONE = auto()
    SETTLED = auto()
    ROUND_RESET = auto()


TRANSITIONS: dict[tuple[TableState, TableEvent], TableState] = {
    (TableState.IDLE, TableEvent.PLAYERS_SEATED): TableState.BETTING_OPEN,
    (TableState.BETTING_OPEN, TableEvent.BETS_LOCKED): TableState.BETTING_CLOSED,
    (TableState.BETTING_CLOSED, TableEvent.START_DEAL): TableState.DEALING,
    (TableState.DEALING, TableEvent.DEAL_COMPLETE): TableState.PLAYER_TURNS,
    (TableState.PLAYER_TURNS, TableEvent.ALL_PLAYERS_DONE): TableState.DEALER_TURN,
    (TableState.DEALER_TURN, TableEvent.DEALER_DONE): TableState.SETTLEMENT,
    (TableState.SETTLEMENT, TableEvent.SETTLED): TableState.IDLE,
}


class InvalidTransition(Exception):
    pass


class StateMachine:
    def __init__(self, initial: TableState = TableState.IDLE):
        self.state = initial

    def can_fire(self, event: TableEvent) -> bool:
        return (self.state, event) in TRANSITIONS

    def fire(self, event: TableEvent) -> TableState:
        key = (self.state, event)
        if key not in TRANSITIONS:
            raise InvalidTransition(f"Cannot fire {event} from {self.state}")
        self.state = TRANSITIONS[key]
        return self.state
