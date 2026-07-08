"""GameSession, Round, and Seat/Participation ORM models.

TODO:
- GameSession ("shoe"): id, table_id, started_at, ended_at, deck_seed/shuffle metadata
- Round: id, table_id, session_id, dealer_hand (json), status, started_at, ended_at
- Seat/Participation: id, round_id, user_id, seat_number, bet_amount, hand(s) (json,
  supports splits), outcome (win/lose/push/blackjack/bust), payout
"""
