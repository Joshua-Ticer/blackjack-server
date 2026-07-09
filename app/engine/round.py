"""Pure orchestrator tying deck/hand/rules/state_machine/dealer into one round.

No I/O. Given a seed and a scripted sequence of player actions, a Round's outcome must
be fully deterministic and reproducible -- this is what makes Phase 1 "done": a full
multi-player round playable from a plain Python script/REPL, no server involved.

TODO:
- Round class: deal(), accept a player action for the seat-to-act, settle()
- Settlement math: win/lose/push/blackjack payout, using the ratio chosen in rules.py
"""

from dataclasses import dataclass, field

from .card import Card
from .deck import Shoe
from .hand import Hand
from .rules import Action, TableRules, legal_actions
from .dealer import play_dealer_hand
from .state_machine import StateMachine, TableEvent, TableState
from .settlement import Outcome, SettlementResult, settle_hand


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RoundError(Exception):
    """Base class for all round-level errors."""


class IllegalActionError(RoundError):
    def __init__(self, action: Action, legal: set[Action]):
        self.action = action
        self.legal = legal
        super().__init__(f"Action {action} not legal; legal actions: {legal}")


class SeatNotFoundError(RoundError):
    pass


class InvalidBetError(RoundError):
    pass


# ---------------------------------------------------------------------------
# Seat
# ---------------------------------------------------------------------------

@dataclass
class Seat:
    player_id: str
    hands: list[Hand] = field(default_factory=lambda: [Hand()])
    bets: list[int] = field(default_factory=lambda: [0])
    active_hand_index: int = 0
    surrendered_hands: set[int] = field(default_factory=set)
    standing_hands: set[int] = field(default_factory=set)
    doubled_hands: set[int] = field(default_factory=set)
    split_aces_hands: set[int] = field(default_factory=set)
    total_splits: int = 0

    def is_hand_done(self, index: int) -> bool:
        hand = self.hands[index]
        return (
            hand.is_bust
            or hand.is_blackjack
            or index in self.standing_hands
            or index in self.surrendered_hands
            or index in self.doubled_hands       # double = exactly one more card, then done
            or index in self.split_aces_hands     # split aces = exactly one card, then done
        )

    def all_hands_done(self) -> bool:
        return all(self.is_hand_done(i) for i in range(len(self.hands)))

    def next_active_hand_index(self) -> int | None:
        """Return the next hand index that still needs action, or None if all done."""
        for i in range(len(self.hands)):
            if not self.is_hand_done(i):
                return i
        return None


# ---------------------------------------------------------------------------
# Round
# ---------------------------------------------------------------------------

class Round:
    def __init__(self, shoe: Shoe, rules: TableRules, seats: list[Seat]):
        self.shoe = shoe
        self.rules = rules
        self.seats = seats
        self.dealer_hand = Hand()
        self.sm = StateMachine(initial=TableState.BETTING_CLOSED)
        self._settled = False

    # -- Dealing -----------------------------------------------------------

    def deal_initial(self) -> None:
        """Deal two cards to each seat's first hand and two to the dealer.
        Fires START_DEAL then DEAL_COMPLETE since neither step requires
        external input -- they're system-driven and chained immediately."""
        self.sm.fire(TableEvent.START_DEAL)

        for _ in range(2):
            for seat in self.seats:
                seat.hands[0].add(self.shoe.draw())
            self.dealer_hand.add(self.shoe.draw())

        self.sm.fire(TableEvent.DEAL_COMPLETE)

    # -- Player actions ------------------------------------------------------

    def _get_seat(self, player_id: str) -> Seat:
        for seat in self.seats:
            if seat.player_id == player_id:
                return seat
        raise SeatNotFoundError(player_id)

    def legal_actions_for(self, player_id: str) -> set[Action]:
        seat = self._get_seat(player_id)
        index = seat.active_hand_index
        hand = seat.hands[index]

        is_first_action = len(hand.cards) == 2 and index not in self._acted_hands(seat)
        is_split_aces_hand = index in seat.split_aces_hands

        return legal_actions(
            hand=hand,
            rules=self.rules,
            is_first_action=is_first_action,
            split_count=seat.total_splits,
            is_split_aces_hand=is_split_aces_hand,
        )

    def _acted_hands(self, seat: Seat) -> set[int]:
        """Hands that have already had a non-split, non-initial action taken
        (used to determine whether double/surrender/split are still legal)."""
        return seat.doubled_hands | seat.standing_hands

    def player_action(self, player_id: str, action: Action) -> None:
        seat = self._get_seat(player_id)
        index = seat.active_hand_index
        hand = seat.hands[index]

        legal = self.legal_actions_for(player_id)
        if action not in legal:
            raise IllegalActionError(action, legal)

        if action == Action.HIT:
            hand.add(self.shoe.draw())

        elif action == Action.STAND:
            seat.standing_hands.add(index)

        elif action == Action.DOUBLE:
            seat.bets[index] *= 2
            hand.add(self.shoe.draw())
            seat.doubled_hands.add(index)

        elif action == Action.SURRENDER:
            seat.surrendered_hands.add(index)

        elif action == Action.SPLIT:
            self._split_hand(seat, index)

        self._advance_seat_if_needed(seat)

    def _split_hand(self, seat: Seat, index: int) -> None:
        original = seat.hands[index]
        card_a, card_b = original.cards[0], original.cards[1]
        splitting_aces = card_a.rank.name == "ACE"

        new_hand_a = Hand([card_a])
        new_hand_b = Hand([card_b])

        new_hand_a.add(self.shoe.draw())
        new_hand_b.add(self.shoe.draw())

        seat.hands[index] = new_hand_a
        seat.hands.insert(index + 1, new_hand_b)

        original_bet = seat.bets[index]
        seat.bets.insert(index + 1, original_bet)

        # shift any tracked indices at/after the insertion point up by one so
        # they still refer to the correct hand after the insert
        seat.standing_hands = self._shift_indices(seat.standing_hands, index)
        seat.doubled_hands = self._shift_indices(seat.doubled_hands, index)
        seat.surrendered_hands = self._shift_indices(seat.surrendered_hands, index)
        seat.split_aces_hands = self._shift_indices(seat.split_aces_hands, index)

        if splitting_aces:
            seat.split_aces_hands.add(index)
            seat.split_aces_hands.add(index + 1)

        seat.total_splits += 1

    @staticmethod
    def _shift_indices(indices: set[int], from_index: int) -> set[int]:
        return {i + 1 if i > from_index else i for i in indices}

    def _advance_seat_if_needed(self, seat: Seat) -> None:
        """Move to the next un-finished hand at this seat, if the current
        one is done."""
        if seat.is_hand_done(seat.active_hand_index):
            next_index = seat.next_active_hand_index()
            if next_index is not None:
                seat.active_hand_index = next_index

    def all_seats_done(self) -> bool:
        return all(seat.all_hands_done() for seat in self.seats)

    def advance_to_dealer_turn(self) -> None:
        """Call once all_seats_done() is True."""
        self.sm.fire(TableEvent.ALL_PLAYERS_DONE)
        self._play_dealer()

    # -- Dealer --------------------------------------------------------------

    def _play_dealer(self) -> None:
        any_player_still_in = any(
            not (i in seat.surrendered_hands or hand.is_bust)
            for seat in self.seats
            for i, hand in enumerate(seat.hands)
        )
        if any_player_still_in:
            play_dealer_hand(self.dealer_hand, self.shoe, self.rules)

        self.sm.fire(TableEvent.DEALER_DONE)

    # -- Settlement ------------------------------------------------------

    def settle(self) -> list[SettlementResult]:
        if self._settled:
            raise RoundError("Round already settled")

        dealer_total = self.dealer_hand.total
        dealer_bust = self.dealer_hand.is_bust
        dealer_blackjack = self.dealer_hand.is_blackjack

        results: list[SettlementResult] = []

        for seat in self.seats:
            for i, hand in enumerate(seat.hands):
                results.append(settle_hand(
                    rules=self.rules,
                    player_id=seat.player_id,
                    hand_index=i,
                    hand=hand,
                    bet=seat.bets[i],
                    dealer_total=dealer_total,
                    dealer_bust=dealer_bust,
                    dealer_blackjack=dealer_blackjack,
                    surrendered=i in seat.surrendered_hands,
                ))

        self.sm.fire(TableEvent.SETTLED)
        self._settled = True
        return results