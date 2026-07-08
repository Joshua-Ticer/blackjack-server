# ADR 0002: Chip balances are ledger-derived, not mutated in place

## Status
Proposed

## Context
Chip balances are effectively money-like data: they must never silently drift, must be
auditable, and must survive concurrent writers (gameplay settlement, admin adjustments,
buy-ins) without corruption.

## Decision
Every chip movement is written as an append-only `LedgerEntry` row (bet, payout, buy-in,
adjustment) inside the same DB transaction as the round/status update it belongs to. A
user's `chip_balance` is either fully derived by summing their ledger entries, or a
cached column that is reconciled from the ledger and never written to directly by game
logic.

## Consequences
- Full audit trail "for free" -- any balance at any point in time is reconstructable.
- Settlement must be atomic: multiple ledger writes + round status update happen in one
  transaction, or not at all.
- Any code path that touches balance outside the single-writer table actor (e.g., an
  admin adjustment endpoint) must still be safe under concurrent access -- use
  `SELECT ... FOR UPDATE` or an atomic `UPDATE ... WHERE balance >= amount RETURNING`
  rather than a read-then-write.

## Alternatives considered
- **Mutate `user.chip_balance` directly**: simplest to write, but loses the audit trail
  and reintroduces the exact "read-modify-write" race this project is meant to
  demonstrate avoiding.
