"""Append-only LedgerEntry ORM model -- the audit trail for every chip movement.

Design principle (state it in the README too): balances are never mutated in-place by
game logic alone -- every chip movement is a LedgerEntry, and a user's chip_balance is
either a cached column reconciled from the ledger or fully derived from summing entries.

TODO fields: id, user_id, round_id (nullable), amount, type (bet/payout/buy-in/
adjustment), balance_after, created_at
"""
