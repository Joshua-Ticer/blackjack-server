"""Bet placement: validates against the ledger, locks the bet, emits a state_delta.

TODO:
- place_bet(user, table, amount, action_id) -> dedupe by action_id within the round,
  validate amount against min/max and current ledger-derived balance
"""
