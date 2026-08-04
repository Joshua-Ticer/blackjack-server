from __future__ import annotations

from app.engine.card import RANK_VALUES, Rank, Suit

CARD_WIDTH = 7
CARD_HEIGHT = 5

SUIT_NAMES = {
    Suit.HEARTS: "hearts",
    Suit.DIAMONDS: "diamonds",
    Suit.CLUBS: "clubs",
    Suit.SPADES: "spades",
}

RED_SUITS = (Suit.HEARTS, Suit.DIAMONDS)


class CardParseError(ValueError):
    pass


def parse_card(text: str) -> tuple[Rank, Suit]:
    if len(text) < 2:
        raise CardParseError(text)
    rank_part, suit_part = text[:-1], text[-1]
    try:
        return Rank(rank_part), Suit(suit_part)
    except ValueError as exc:
        raise CardParseError(text) from exc


def is_red(text: str) -> bool:
    return parse_card(text)[1] in RED_SUITS


def hand_total(cards: list[str]) -> int:
    total = 0
    aces = 0
    for text in cards:
        rank, _ = parse_card(text)
        total += RANK_VALUES[rank]
        if rank is Rank.ACE:
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def is_soft(cards: list[str]) -> bool:
    hard = sum(RANK_VALUES[parse_card(c)[0]] for c in cards)
    return any(parse_card(c)[0] is Rank.ACE for c in cards) and hard <= 21


def is_bust(cards: list[str]) -> bool:
    return hand_total(cards) > 21


def is_blackjack(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_total(cards) == 21


def total_label(cards: list[str]) -> str:
    if not cards:
        return ""
    if is_blackjack(cards):
        return "BLACKJACK"
    total = hand_total(cards)
    if total > 21:
        return f"{total} BUST"
    if is_soft(cards):
        return f"soft {total}"
    return str(total)


def card_lines(text: str) -> list[str]:
    rank, suit = parse_card(text)
    inner = CARD_WIDTH - 2
    return [
        "╭" + "─" * inner + "╮",
        "│" + rank.value.ljust(inner) + "│",
        "│" + suit.value.center(inner) + "│",
        "│" + rank.value.rjust(inner) + "│",
        "╰" + "─" * inner + "╯",
    ]


def face_down_lines() -> list[str]:
    fill = "░" * (CARD_WIDTH - 2)
    return [
        "╭" + "─" * (CARD_WIDTH - 2) + "╮",
        "│" + fill + "│",
        "│" + fill + "│",
        "│" + fill + "│",
        "╰" + "─" * (CARD_WIDTH - 2) + "╯",
    ]
