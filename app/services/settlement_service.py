"""Round settlement: computes outcomes, writes ledger entries + round history
transactionally (all-or-nothing -- partial failure must not corrupt state).

TODO:
- settle_round(round) -> writes LedgerEntry rows + Round status update in one DB
  transaction, then returns the round_result payload for broadcast
"""
