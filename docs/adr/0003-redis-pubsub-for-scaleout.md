# ADR 0003: Redis pub/sub for cross-instance broadcast

## Status
Proposed

## Context
The single-writer-per-table model (ADR 0001) works within one process. Running multiple
app instances for horizontal scale means a client's WebSocket connection may be held by
an instance that does not own that client's table's `TableActor`.

## Decision
Each table is owned by exactly one instance's actor at a time, via a lock/lease held in
Redis. Other instances relay client actions for that table over a Redis pub/sub channel
to the owning instance, and relay broadcasts back out to their own locally-connected
clients over the same mechanism.

## Consequences
- Enables horizontal scaling of a stateful WebSocket service without every instance
  needing a direct connection to every table's actor.
- Introduces a new failure mode: what happens if the owning instance dies mid-round?
  Mitigated by periodic snapshotting to Redis (ADR 0004) so a new owner can resume.
- Adds a small amount of relay latency for clients not co-located with their table's
  owning instance -- acceptable given human reaction-time action rates.

## Alternatives considered
- **Sticky routing at the load balancer** (pin a client to the instance owning their
  table): avoids the relay hop, but complicates the load balancer and doesn't solve the
  case where two players from different instances are at the same table.
- **A dedicated actor framework / message broker** (e.g., Ray, a full event bus):
  more powerful, but overkill for this project's scale and a bigger operational surface
  to run and explain.
