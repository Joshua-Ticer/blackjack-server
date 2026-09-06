"""Dealer's fixed strategy (hit until 17; stand-on-soft-17 policy documented in rules.py).

TODO:
- play_dealer_hand(hand: Hand, shoe: list[Card]) -> Hand
"""

from .deck import Shoe
from .hand import Hand
from .rules import TableRules


def play_dealer_hand(hand: Hand, shoe: Shoe, rules: TableRules) -> Hand:
    while hand.total < 17 or (
        hand.total == 17 and hand.is_soft and rules.dealer_hits_soft_17
    ):
        hand.add(shoe.draw())
    return hand
