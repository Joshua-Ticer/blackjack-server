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
