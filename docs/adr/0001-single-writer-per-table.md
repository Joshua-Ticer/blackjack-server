# ADR 0001: Single-writer-per-table concurrency model

## Status
Proposed

## Context
Multiple players can act on the same table "simultaneously." Naive shared-mutable-state
handling (each WebSocket handler mutating table state directly) reintroduces classic
race conditions: two `hit` requests from the same seat, a bet placed twice, an action
applied against a stale snapshot.

## Decision
Each table's mutable state is owned by exactly one asyncio task (a `TableActor`). All
events for that table -- bets, actions, joins -- are pushed onto that actor's
`asyncio.Queue` and processed strictly sequentially. No shared-memory locking is needed
within a process because there is no concurrent mutation, only serialized processing.

## Consequences
- Within one process, table-level race conditions collapse to a non-issue by
  construction, not by careful locking discipline.
- Throughput per table is bounded by single-task serial processing -- acceptable, since
  a single table's action rate is inherently low (one human acting at a time).
- Horizontal scale-out (multiple app instances) requires an explicit table-ownership
  mechanism, since the in-process queue does not span processes -- see the follow-on ADR
  for Redis pub/sub relay + per-table leases.

## Alternatives considered
- **Per-table asyncio.Lock around shared state**: still requires careful discipline
  everywhere state is touched, and doesn't parallelize better than a queue since it's
  still fully serialized -- the actor gives the same guarantee with less surface area
  for a forgotten lock acquisition.
- **Database-level row locking (`SELECT ... FOR UPDATE`) as the only guard**: too slow
  for in-round gameplay latency; reserved instead for the ledger/balance write path
  where it belongs.
