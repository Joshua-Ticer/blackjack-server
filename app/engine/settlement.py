from dataclasses import dataclass
from enum import Enum

class Outcome(Enum):
    WIN = "win"
    LOSS = "loss"
    PUSH = "push"
    BLACKJACK = "blackjack"
    BUST = "bust"
    SURRENDER = "surrender"

@dataclass(frozen=True)
class SettlementResult:
    player_id: str
    hand_index: int          # which hand, in case of splits
    bet: int
    outcome: Outcome
    payout: int               # total chips returned to player, 0 if loss
    net: int                  # payout - bet; negative on loss, 0 on push


def settle_hand(
    rules: TableRules,
    player_id: str,
    hand_index: int,
    hand: Hand,
    bet: int,
    dealer_total: int,
    dealer_bust: bool,
    dealer_blackjack: bool,
    surrendered: bool = False,
) -> SettlementResult:
    if surrendered:
        payout = bet // 2
        return SettlementResult(
            player_id, hand_index, bet, Outcome.SURRENDER,
            payout=payout, net=-(bet - payout),
        )

    if hand.is_bust:
        return SettlementResult(
            player_id, hand_index, bet, Outcome.BUST, payout=0, net=-bet
        )

    if hand.is_blackjack and not dealer_blackjack:
        num, den = rules.blackjack_payout
        payout = bet + (bet * num) // den
        return SettlementResult(
            player_id, hand_index, bet, Outcome.BLACKJACK,
            payout=payout, net=payout - bet,
        )

    if hand.is_blackjack and dealer_blackjack:
        return SettlementResult(
            player_id, hand_index, bet, Outcome.PUSH, payout=bet, net=0
        )

    if dealer_bust:
        return SettlementResult(
            player_id, hand_index, bet, Outcome.WIN, payout=bet * 2, net=bet
        )

    if hand.total > dealer_total:
        return SettlementResult(
            player_id, hand_index, bet, Outcome.WIN, payout=bet * 2, net=bet
        )

    if hand.total == dealer_total:
        return SettlementResult(
            player_id, hand_index, bet, Outcome.PUSH, payout=bet, net=0
        )

    return SettlementResult(
        player_id, hand_index, bet, Outcome.LOSS, payout=0, net=-bet
    )