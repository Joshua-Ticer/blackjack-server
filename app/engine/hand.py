"""Hand value calculation, including soft/hard totals via Ace-as-1-or-11.

TODO:
- Hand class holding an ordered list of Card
- value() -> int   (best legal total, computed generically -- do not hardcode ace=11
  and special-case everywhere; count aces and adjust)
- is_soft() -> bool
- is_bust() -> bool
- is_blackjack() -> bool  (natural 21 on the first two cards only)
"""

class Hand:
    def __init__(self, cards: list[Card] | None = None):
        self.cards: list[Card] = cards or []

    def add(self, card: Card) -> None:
        self.cards.append(card)
    
    @property
    def hard_total(self) -> int:
        return sum(c.value for c in self.cards)

    @property
    def num_aces(self) -> int:
        return sum(1 for c in self.cards if c.rank == Rank.ACE)
    
    @property
    def total(self) -> int:
        total = self.hard_total
        aces = self.num_aces
        while total > 21 and aces > 0:
            total -= 10  
            aces -= 1
        return total
    
    @property
    def is_soft(self) -> bool:
        return self.num_aces > 0 and self.total <= 21

    @property
    def is_bust(self) -> bool:
        return self.total > 21

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total == 21
    
    @property
    def can_split(self) -> bool:
        return len(self.cards) == 2 and self.cards[0].rank == self.cards[1].rank