"""Card representation. Pure data, no I/O."""

from enum import Enum
from dataclasses import dataclass


class Suit(Enum):
    HEARTS = "H"
    CLUBS = "C"
    DIAMONDS = "D"
    SPADES = "S"


class Rank(Enum):
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"


# Blackjack values, kept separate from Rank's own values so JACK/QUEEN/KING
# stay distinct enum members (equal Enum values collapse into aliases and
# vanish from `for r in Rank` iteration, which silently shrinks the shoe).
RANK_VALUES: dict[Rank, int] = {
    Rank.TWO: 2,
    Rank.THREE: 3,
    Rank.FOUR: 4,
    Rank.FIVE: 5,
    Rank.SIX: 6,
    Rank.SEVEN: 7,
    Rank.EIGHT: 8,
    Rank.NINE: 9,
    Rank.TEN: 10,
    Rank.JACK: 10,
    Rank.QUEEN: 10,
    Rank.KING: 10,
    Rank.ACE: 11,
}


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: Rank

    @property
    def value(self) -> int:
        return RANK_VALUES[self.rank]

    def __str__(self) -> str:
        return f"{self.rank.value}{self.suit.value}"

    @classmethod
    def parse(cls, text: str) -> "Card":
        return cls(rank=Rank(text[:-1]), suit=Suit(text[-1]))
