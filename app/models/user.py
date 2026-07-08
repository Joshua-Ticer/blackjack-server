"""User ORM model.

TODO fields: id, username, hashed_password, email, chip_balance, created_at
Note: chip_balance should be treated as a cached/reconciled column derived from
LedgerEntry rows, never mutated directly by game logic -- see models/ledger.py.
"""
