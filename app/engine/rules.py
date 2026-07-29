"""Legal-action policy: what a player may do given a hand and table rules.

Document the rule set chosen here (this file is the source of truth referenced by
docs/adr/):
- Blackjack payout ratio: 3:2 or 6:5 -- TODO decide and document
- Dealer stands on soft 17? -- TODO decide and document
- Double-after-split allowed? -- TODO decide and document
- Split aces: one card only, no re-split? -- TODO decide and document
- Surrender: allowed, and late vs. early? -- TODO decide and document

TODO:
- legal_actions(hand, table_rules) -> set[Action]
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .hand import Hand


class Action(Enum):
    HIT = 'hit'
    STAND = 'stand'
    DOUBLE = 'double'
    SPLIT = 'split'
    SURRENDER = 'surrender'

@dataclass(frozen=True)
class TableRules:
    blackjack_payout: tuple[int, int] = (3, 2)
    dealer_hits_soft_17: bool = False
    double_after_split_allowed: bool = True
    resplit_aces_allowed: bool = False
    max_splits: int = 3
    late_surrender_allowed: bool = True

def legal_actions(
    hand: Hand,
    rules: TableRules,
    is_first_action: bool,
    split_count: int,
    is_split_aces_hand: bool,
) -> set[Action]:
    if hand.is_bust or hand.is_blackjack:
        return set()

    if is_split_aces_hand:
        # split aces conventionally get exactly one card, no further action
        return set()

    actions = {Action.HIT, Action.STAND}

    if is_first_action:
        actions.add(Action.DOUBLE)
        if rules.late_surrender_allowed and split_count == 0:
            actions.add(Action.SURRENDER)
        if hand.can_split and split_count < rules.max_splits:
            actions.add(Action.SPLIT)

    return actions