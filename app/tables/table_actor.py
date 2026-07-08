"""Single-writer-per-table actor: one asyncio task processes this table's event queue
serially, so no explicit locking is needed within a process -- see docs/adr/ for the
single-writer-per-table decision.

TODO:
- TableActor wrapping an asyncio.Queue + a run loop + the engine.Round it owns
- apply(event) -> broadcasts the resulting state_delta to connected clients
- snapshot() / restore()  -- periodic Redis-backed persistence for crash recovery (Phase 5)
"""
