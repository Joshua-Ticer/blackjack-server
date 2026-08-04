from __future__ import annotations

import pytest

from app.tui.cards import (
    CardParseError,
    hand_total,
    is_blackjack,
    is_red,
    parse_card,
    total_label,
)
from app.tui.protocol import TableModel
from tests.tui.fakes import (
    ME,
    OTHER,
    action_applied,
    bet_placed,
    betting_open,
    error,
    player_turn,
    round_result,
    seat,
    table_state,
)


@pytest.fixture
def model() -> TableModel:
    return TableModel(me=ME)


# --- card parsing -----------------------------------------------------------


def test_ten_parses_as_three_character_card():
    rank, suit = parse_card("10H")
    assert (rank.value, suit.value) == ("10", "H")


def test_two_character_cards_parse():
    assert parse_card("AS")[0].value == "A"
    assert parse_card("7C")[1].value == "C"


def test_malformed_card_raises():
    with pytest.raises(CardParseError):
        parse_card("XX")


def test_hearts_and_diamonds_are_red():
    assert is_red("AH") and is_red("10D")
    assert not is_red("AS") and not is_red("7C")


def test_ace_downgrades_to_avoid_bust():
    assert hand_total(["AS", "9H", "5C"]) == 15


def test_soft_and_blackjack_labels():
    assert total_label(["AS", "6H"]) == "soft 17"
    assert total_label(["AS", "KH"]) == "BLACKJACK"
    assert total_label(["10S", "9H", "5C"]) == "24 BUST"
    assert is_blackjack(["AS", "KH"])


# --- reducer ----------------------------------------------------------------


def test_table_state_populates_seats_and_version(model: TableModel):
    model.apply(table_state(
        lobby_state="player_turns",
        seats=[seat(ME, hands=[["7C", "9S"]], bets=[25])],
        dealer_hand=["AC"],
        state_version=4,
    ))
    assert model.lobby_state == "player_turns"
    assert model.state_version == 4
    assert model.my_seat is not None
    assert model.my_seat.hands == [["7C", "9S"]]
    assert model.seated is True


def test_state_version_never_moves_backwards(model: TableModel):
    model.apply(table_state(state_version=9))
    model.apply(table_state(state_version=3))
    assert model.state_version == 9


def test_dealer_upcard_stays_hidden_until_round_result(model: TableModel):
    model.apply(table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=4))
    assert model.visible_dealer_cards() == ["AC"]
    assert model.dealer_face_down() == 1
    assert model.dealer_revealed is False

    model.apply(round_result(dealer_hand=["AC", "KC"]))
    assert model.dealer_revealed is False
    assert model.advance_dealer_reveal() is True
    assert model.visible_dealer_cards() == ["AC", "KC"]
    assert model.dealer_face_down() == 0


def test_dealer_reveals_one_card_at_a_time(model: TableModel):
    model.apply(table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=4))
    model.apply(round_result(dealer_hand=["AC", "KC", "5D"]))

    assert model.visible_dealer_cards() == ["AC"]
    assert model.advance_dealer_reveal() is False
    assert model.visible_dealer_cards() == ["AC", "KC"]
    assert model.advance_dealer_reveal() is True
    assert model.visible_dealer_cards() == ["AC", "KC", "5D"]


def test_outcome_is_withheld_until_the_reveal_finishes(model: TableModel):
    model.apply(table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=4))
    model.apply(round_result(dealer_hand=["AC", "KC", "5D"], outcome="win"))

    assert model.results is not None
    assert model.settlement_visible is False
    assert model.visible_results() == []

    model.advance_dealer_reveal()
    assert model.visible_results() == []

    model.advance_dealer_reveal()
    assert model.settlement_visible is True
    assert model.visible_results()[0].outcome == "win"


def test_reveal_is_idempotent_once_complete(model: TableModel):
    model.apply(table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=4))
    model.apply(round_result(dealer_hand=["AC", "KC"]))
    model.advance_dealer_reveal()
    assert model.advance_dealer_reveal() is True
    assert model.visible_dealer_cards() == ["AC", "KC"]


def test_reconnect_during_settlement_shows_the_hand_already_revealed(model: TableModel):
    model.apply(
        table_state(lobby_state="settlement", dealer_hand=["AC", "KC"], state_version=9)
    )
    assert model.dealer_revealed is True
    assert model.visible_dealer_cards() == ["AC", "KC"]
    assert model.dealer_face_down() == 0


def test_player_turn_with_no_legal_actions_is_not_a_turn(model: TableModel):
    model.apply(player_turn(player_id=ME, legal_actions=[]))
    assert model.is_my_turn is False
    assert model.legal_actions() == ()


def test_player_turn_for_me_sets_legal_actions(model: TableModel):
    model.apply(player_turn(player_id=ME, legal_actions=["hit", "stand", "double"]))
    assert model.is_my_turn
    assert model.can("hit") and model.can("double")
    assert not model.can("split")


def test_player_turn_for_another_player_is_ignored(model: TableModel):
    model.apply(player_turn(player_id=OTHER, legal_actions=["hit", "stand"]))
    assert not model.is_my_turn
    assert model.legal_actions() == ()
    assert not model.can("hit")


def test_bet_placed_for_me_updates_my_bet(model: TableModel):
    model.apply(betting_open())
    model.apply(bet_placed(player_id=ME, amount=40))
    assert model.my_bet == 40


def test_bet_placed_for_other_player_does_not_touch_my_bet(model: TableModel):
    model.apply(betting_open())
    model.apply(bet_placed(player_id=OTHER, amount=40))
    assert model.my_bet == 0
    assert model._seat_for(OTHER).bets == [40]


def test_action_applied_updates_hand_and_clears_my_turn(model: TableModel):
    model.apply(player_turn(player_id=ME))
    model.apply(action_applied(player_id=ME, hand=["7C", "9S", "5D"]))
    assert model.my_seat is not None
    assert model.my_seat.hands[0] == ["7C", "9S", "5D"]
    assert not model.is_my_turn


def test_result_survives_the_betting_open_that_follows_it(model: TableModel):
    model.apply(round_result(dealer_hand=["AC", "KC"]))
    model.apply(betting_open())
    assert model.my_results()[0].outcome == "win"
    assert model.betting is not None
    assert model.betting.min_bet == 5
    assert model.my_bet == 0


def test_result_is_cleared_when_the_next_round_deals(model: TableModel):
    model.apply(round_result(dealer_hand=["AC", "KC"]))
    model.apply(betting_open())
    model.apply(table_state(lobby_state="player_turns", dealer_hand=["7D"], state_version=30))
    assert model.results is None
    assert model.dealer_revealed is False
    assert model.dealer_hand == ["7D"]


def test_empty_round_result_does_not_wipe_my_last_outcome(model: TableModel):
    model.apply(round_result(outcome="win", dealer_hand=["AC", "KC"]))
    model.apply({"type": "round_result", "results": [], "dealer_hand": [], "state_version": 40})
    assert model.my_results()[0].outcome == "win"


def test_round_result_records_my_outcome(model: TableModel):
    model.apply(round_result(outcome="blackjack", net=37, balance_after=1037))
    mine = model.my_results()
    assert len(mine) == 1
    assert mine[0].outcome == "blackjack"
    assert mine[0].balance_after == 1037


def test_round_result_for_other_player_is_not_mine(model: TableModel):
    model.apply(round_result(player_id=OTHER))
    assert model.results is not None
    assert model.my_results() == []


def test_error_is_captured(model: TableModel):
    model.apply(error("betting is closed"))
    assert model.error == "betting is closed"


def test_leaving_player_turns_clears_turn(model: TableModel):
    model.apply(player_turn(player_id=ME))
    assert model.is_my_turn
    model.apply(table_state(lobby_state="idle", state_version=99))
    assert not model.is_my_turn


def test_active_deadline_prefers_turn_over_betting(model: TableModel):
    model.apply(betting_open(seconds=15))
    betting_deadline = model.active_deadline()
    model.apply(player_turn(seconds=30))
    assert model.active_deadline() != betting_deadline
    assert model.active_deadline() == model.turn.deadline


def test_unknown_message_type_is_ignored(model: TableModel):
    model.apply({"type": "betting_closed", "state_version": 7})
    assert model.state_version == 7
    model.apply({"type": "pong"})
