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
