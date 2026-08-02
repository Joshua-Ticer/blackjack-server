"""Shoe/deck construction and seeded shuffling.

TODO:
- build_shoe(num_decks: int) -> list[Card]
- shuffle(shoe: list[Card], seed: int | None) -> list[Card]  (seeded for reproducible tests)
- cut card / penetration handling (when to trigger a reshuffle)
"""


import random

from .card import Card, Rank, Suit


class Shoe:
    def __init__(self, num_decks: int = 6, seed: int | None = None):
        self._num_decks = num_decks
        self._rng = random.Random(seed)
        self._cards: list[Card] = self._build_shoe(num_decks)
        self._total = len(self._cards)
        self._rng.shuffle(self._cards)

    def _build_shoe(self, num_decks: int) -> list[Card]:
        return [Card(s, r) for _ in range(num_decks) for s in Suit for r in Rank]

    def draw(self) -> Card:
        if not self._cards:
            self._cards = self._build_shoe(self._num_decks)
            self._rng.shuffle(self._cards)
        return self._cards.pop()

    def cards_remaining(self) -> int:
        return len(self._cards)

    def needs_shuffle(self, penetration: float) -> bool:
        return self.cards_remaining() <= self._total * (1 - penetration)