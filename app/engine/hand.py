"""Hand value calculation, including soft/hard totals via Ace-as-1-or-11.

TODO:
- Hand class holding an ordered list of Card
- value() -> int   (best legal total, computed generically -- do not hardcode ace=11
  and special-case everywhere; count aces and adjust)
- is_soft() -> bool
- is_bust() -> bool
- is_blackjack() -> bool  (natural 21 on the first two cards only)
"""
