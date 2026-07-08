# ADR 0004: Reconnect via full snapshot, not event replay

## Status
Proposed

## Context
A player's WebSocket connection can drop mid-round (network blip, phone lock, laptop
sleep). On reconnect, the client needs to end up in a state consistent with the table's
current reality.

## Decision
On reconnect, the client sends `join_table` (optionally with a session token); the
server responds with a full `table_state` snapshot rebuilt from in-memory/Redis state,
rather than replaying every `state_delta` event since disconnect. Every snapshot and
delta carries a monotonic `state_version`; the client (and server) can detect and ignore
messages referencing a stale version -- this also closes the "stale action from an old
connection arrives after an auto-stand fired" race.

## Consequences
- Much simpler client and server logic than event replay: no need to buffer, persist,
  or replay a per-client event log.
- Trade-off: the client does not get a full history of everything that happened while
  disconnected, only the current state -- acceptable for gameplay (the current hand and
  legal actions are all that matter), not acceptable if full replayability were a
  requirement.
- Crash recovery (server process restart) uses the same mechanism: periodically persist
  a compact snapshot to Redis on every state transition, and a restarted worker resumes
  from that snapshot instead of losing the round.

## Alternatives considered
- **Event sourcing** (persist every event, replay to rebuild state): gives full
  replayability and audit at the event level, but is meaningfully more complex to build
  and operate correctly (event schema versioning, replay performance) for a project
  where round-level ledger history already satisfies the audit requirement. Worth
  naming explicitly as a "what I'd do differently at 10x scale" answer.
