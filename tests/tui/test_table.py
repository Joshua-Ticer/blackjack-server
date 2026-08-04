from __future__ import annotations

from textual.pilot import Pilot
from textual.widgets import Button, Input

from app.tui.app import BlackjackApp
from app.tui.screens.lobby import LobbyScreen
from app.tui.screens.table import ACTIONS, TableScreen
from app.tui.transport import TransportClosed
from tests.tui.conftest import is_on_screen, open_table, q, settle, text_of
from tests.tui.fakes import (
    ME,
    OTHER,
    FakeTransport,
    action_applied,
    bet_placed,
    betting_open,
    error,
    player_turn,
    round_result,
    seat,
    table_state,
)


async def feed(pilot: Pilot[None], transport: FakeTransport, *messages: dict) -> None:
    transport.feed(*messages)
    await settle(pilot)


def enabled_actions(pilot: Pilot[None]) -> set[str]:
    return {
        action
        for action, _, _ in ACTIONS
        if not q(pilot, f"#act-{action}", Button).disabled
    }


def screen(pilot: Pilot[None]) -> TableScreen:
    return pilot.app.screen  # type: ignore[return-value]


async def finish_reveal(pilot: Pilot[None]) -> None:
    """Drive the 1s-per-card dealer reveal to completion without waiting on the clock."""
    for _ in range(12):
        if screen(pilot).model.dealer_revealed:
            break
        screen(pilot).reveal_tick()
        await settle(pilot)
    await settle(pilot)


async def type_bet(pilot: Pilot[None], amount: int | str) -> None:
    await pilot.press("b")
    q(pilot, "#bet-input", Input).value = str(amount)
    await pilot.press("enter")
    await settle(pilot)


# --- legal action gating ----------------------------------------------------


async def test_no_actions_enabled_before_your_turn(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, table_state(lobby_state="betting_open"))
        assert enabled_actions(pilot) == set()


async def test_buttons_match_legal_actions_exactly(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand", "double"]))
        assert enabled_actions(pilot) == {"hit", "stand", "double"}


async def test_split_only_enabled_when_offered(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            player_turn(legal_actions=["hit", "stand", "split", "surrender"]),
        )
        assert enabled_actions(pilot) == {"hit", "stand", "split", "surrender"}


async def test_player_turn_for_another_player_does_not_enable_buttons(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(player_id=OTHER, legal_actions=["hit", "stand"]))
        assert enabled_actions(pilot) == set()
        assert not screen(pilot).model.is_my_turn


async def test_illegal_action_keypress_sends_nothing(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"]))
        await pilot.press("p")
        await settle(pilot)
        assert transport.sent_of("action") == []


async def test_legal_action_keypress_sends_action(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"], state_version=5))
        await pilot.press("h")
        await settle(pilot)
        sent = transport.sent_of("action")
        assert len(sent) == 1
        assert sent[0]["action"] == "hit"


async def test_actions_disabled_again_after_acting(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"]))
        await pilot.press("h")
        await settle(pilot)
        assert enabled_actions(pilot) == set()


# --- state_version and action_id -------------------------------------------


async def test_action_echoes_latest_state_version(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"], state_version=5))
        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=11))
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"], state_version=12))
        await pilot.press("h")
        await settle(pilot)
        assert transport.sent_of("action")[0]["state_version"] == 12


async def test_stale_state_version_is_never_sent(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"], state_version=7))
        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=3))
        await pilot.press("h")
        await settle(pilot)
        assert transport.sent_of("action")[0]["state_version"] == 7


async def test_every_intent_carries_a_fresh_action_id(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        for amount in (10, 20, 30):
            await type_bet(pilot, amount)

        ids = [m["action_id"] for m in transport.sent_of("place_bet")]
        assert len(ids) == 3
        assert len(set(ids)) == 3


async def test_rebet_after_rejection_uses_a_fresh_action_id(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await type_bet(pilot, 25)

        await feed(pilot, transport, error("betting is closed"))
        await feed(pilot, transport, betting_open(state_version=20))

        await type_bet(pilot, 25)

        ids = [m["action_id"] for m in transport.sent_of("place_bet")]
        assert len(ids) == 2
        assert ids[0] != ids[1]


# --- betting ----------------------------------------------------------------


async def test_bet_bar_only_visible_while_betting_open(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        assert is_on_screen(pilot, "#bet-bar")

        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=9))
        assert q(pilot, "#bet-bar").display is False


async def test_bet_outside_limits_is_rejected_locally(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open(min_bet=5, max_bet=500))
        await type_bet(pilot, 900)
        assert transport.sent_of("place_bet") == []
        assert "between 5 and 500" in text_of(q(pilot, "#table-error"))


async def test_action_keys_work_after_placing_a_bet(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await type_bet(pilot, 25)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"], state_version=9))
        await pilot.press("s")
        await settle(pilot)
        assert [m["action"] for m in transport.sent_of("action")] == ["stand"]


async def test_bet_input_is_blurred_when_betting_closes(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await pilot.press("b")
        assert pilot.app.screen.focused is q(pilot, "#bet-input", Input)

        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=9))
        assert pilot.app.screen.focused is not q(pilot, "#bet-input", Input)


async def test_controls_stay_on_screen_after_a_round_on_a_small_terminal(
    bj_app: BlackjackApp, transport: FakeTransport
):
    """Regression: the result panel used to push the bet bar off the bottom edge."""
    async with bj_app.run_test(size=(80, 20)) as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[
                    seat(ME, hands=[["AS", "6H", "4D"]], bets=[25]),
                    seat(OTHER, hands=[["10D", "9C"]], bets=[10]),
                ],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        await feed(pilot, transport, round_result(dealer_hand=["AC", "7C", "9H"]))
        await finish_reveal(pilot)
        await feed(pilot, transport, betting_open(state_version=40))

        assert is_on_screen(pilot, "#bet-bar")
        assert is_on_screen(pilot, "#action-bar")
        assert is_on_screen(pilot, "#status-bar")
        assert pilot.app.screen.focused is q(pilot, "#bet-input", Input)


async def test_betting_open_focuses_and_prefills_the_bet_box(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open(min_bet=5, max_bet=500))
        widget = q(pilot, "#bet-input", Input)
        assert pilot.app.screen.focused is widget
        assert widget.value == ""
        assert "enter to bet 5" in text_of(q(pilot, "#bet-hint"))


async def test_next_round_prefills_your_previous_bet(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await type_bet(pilot, 75)

        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=9))
        await feed(pilot, transport, round_result(dealer_hand=["AC", "KC"]))
        await finish_reveal(pilot)
        await feed(pilot, transport, betting_open(state_version=30))

        widget = q(pilot, "#bet-input", Input)
        assert widget.value == ""
        assert pilot.app.screen.focused is widget
        assert "enter to bet 75" in text_of(q(pilot, "#bet-hint"))

        await pilot.press("enter")
        await settle(pilot)
        amounts = [m["amount"] for m in transport.sent_of("place_bet")]
        assert amounts == [75, 75]


async def test_prefill_is_clamped_to_table_limits(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open(min_bet=5, max_bet=500))
        await type_bet(pilot, 400)
        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=9))
        await feed(pilot, transport, betting_open(min_bet=5, max_bet=50, state_version=30))
        assert "enter to bet 50" in text_of(q(pilot, "#bet-hint"))


async def test_bet_hint_confirms_once_placed(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await type_bet(pilot, 25)
        await feed(pilot, transport, bet_placed(player_id=ME, amount=25))
        assert "bet 25 placed" in text_of(q(pilot, "#bet-hint"))


async def test_bet_while_closed_is_not_sent(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, table_state(lobby_state="player_turns", state_version=9))
        screen(pilot).submit_bet()
        await settle(pilot)
        assert transport.sent_of("place_bet") == []


async def test_bet_placed_ack_is_shown(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await feed(pilot, transport, bet_placed(player_id=ME, amount=40))
        assert "bet 40 placed" in text_of(q(pilot, "#bet-hint"))


async def test_another_players_bet_does_not_confirm_mine(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        await feed(pilot, transport, bet_placed(player_id=OTHER, amount=40))
        assert "placed" not in text_of(q(pilot, "#bet-hint"))


# --- dealer hole card -------------------------------------------------------


async def test_hole_card_stays_face_down_during_play(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=6),
        )
        assert screen(pilot).model.dealer_revealed is False
        assert "░" in text_of(q(pilot, "#dealer-hand"))
        assert "showing" in text_of(q(pilot, "#dealer-total"))


async def test_hole_card_flips_on_round_result(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=6),
        )
        await feed(pilot, transport, round_result(dealer_hand=["AC", "KC"]))
        await finish_reveal(pilot)
        dealer = text_of(q(pilot, "#dealer-hand"))
        assert "░" not in dealer
        assert "K" in dealer
        assert screen(pilot).model.dealer_hand == ["AC", "KC"]
        assert screen(pilot).model.dealer_revealed is True


# --- round result -----------------------------------------------------------


async def test_result_panel_hidden_until_round_ends(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, betting_open())
        assert q(pilot, "#result-panel").display is False


async def test_result_panel_shows_outcome_net_and_balance(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            round_result(outcome="win", bet=25, payout=50, net=25, balance_after=1025),
        )
        await finish_reveal(pilot)
        body = text_of(q(pilot, "#result-body"))
        assert "WIN" in body
        assert "+25" in body
        assert "1025" in body
        assert q(pilot, "#result-panel").display is True


async def test_outcome_is_hidden_until_the_dealer_reveal_finishes(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[seat(ME, hands=[["10S", "9D"]], bets=[25])],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        await feed(pilot, transport, round_result(dealer_hand=["AC", "5C", "6D"], outcome="win"))

        assert q(pilot, "#result-panel").display is False
        assert "░" in text_of(q(pilot, "#dealer-hand"))
        assert "WIN" not in text_of(screen(pilot)._seat_panels[ME])

        screen(pilot).reveal_tick()
        await settle(pilot)
        assert q(pilot, "#result-panel").display is False
        assert "░" not in text_of(q(pilot, "#dealer-hand"))

        screen(pilot).reveal_tick()
        await settle(pilot)
        assert q(pilot, "#result-panel").display is True
        assert "WIN" in text_of(q(pilot, "#result-body"))
        assert "WIN" in text_of(screen(pilot)._seat_panels[ME])


async def test_dealer_cards_appear_one_at_a_time(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=6),
        )
        await feed(pilot, transport, round_result(dealer_hand=["AC", "5C", "6D"]))

        assert screen(pilot).model.visible_dealer_cards() == ["AC"]
        screen(pilot).reveal_tick()
        assert screen(pilot).model.visible_dealer_cards() == ["AC", "5C"]
        screen(pilot).reveal_tick()
        assert screen(pilot).model.visible_dealer_cards() == ["AC", "5C", "6D"]
        assert screen(pilot).model.dealer_revealed is True


async def test_chip_balance_only_updates_once_the_reveal_completes(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(lobby_state="player_turns", dealer_hand=["AC"], state_version=6),
        )
        starting = bj_app.user.chip_balance
        await feed(pilot, transport, round_result(dealer_hand=["AC", "KC"], balance_after=1234))

        assert bj_app.user.chip_balance == starting
        await finish_reveal(pilot)
        assert bj_app.user.chip_balance == 1234


async def test_blackjack_never_prompts_for_an_action(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=[], state_version=7))
        assert screen(pilot).model.is_my_turn is False
        assert enabled_actions(pilot) == set()
        await pilot.press("s")
        await settle(pilot)
        assert transport.sent_of("action") == []


async def test_round_result_updates_chip_balance(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, round_result(balance_after=1234))
        await finish_reveal(pilot)
        assert bj_app.user is not None
        assert bj_app.user.chip_balance == 1234


async def test_another_players_result_is_not_shown_as_mine(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, round_result(player_id=OTHER))
        assert q(pilot, "#result-panel").display is False


# --- errors and reconnect ---------------------------------------------------


async def test_error_mid_round_is_displayed(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"]))
        await feed(pilot, transport, error("Action not legal"))
        assert "Action not legal" in text_of(q(pilot, "#table-error"))


async def test_socket_drop_mid_turn_is_reported(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"]))
        transport.drop(1006)
        await settle(pilot)
        assert "reconnect" in text_of(q(pilot, "#table-error"))
        assert screen(pilot).session.connected is False


async def test_reconnect_resyncs_with_join_table(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(pilot, transport, player_turn(legal_actions=["hit", "stand"]))
        transport.drop(1006)
        await settle(pilot)

        transport.sent.clear()
        await pilot.press("ctrl+r")
        await settle(pilot)

        assert transport.connect_count == 2
        assert transport.sent_of("join_table")

        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[seat(ME, hands=[["7C", "9S"]], bets=[25])],
                dealer_hand=["AC"],
                state_version=30,
            ),
        )
        model = screen(pilot).model
        assert model.state_version == 30
        assert model.my_seat is not None
        assert model.my_seat.hands == [["7C", "9S"]]


async def test_bad_token_close_code_is_explained(bj_app: BlackjackApp, transport: FakeTransport):
    transport.connect_error = TransportClosed(4401)
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        assert "authentication rejected" in text_of(q(pilot, "#table-error"))


async def test_unknown_table_close_code_is_explained(
    bj_app: BlackjackApp, transport: FakeTransport
):
    transport.connect_error = TransportClosed(4404)
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        assert "table not found" in text_of(q(pilot, "#table-error"))


# --- seats and navigation ---------------------------------------------------


async def test_seats_render_for_every_player(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[
                    seat(ME, hands=[["7C", "9S"]], bets=[25]),
                    seat(OTHER, hands=[["10H", "6D"]], bets=[10]),
                ],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        panels = screen(pilot)._seat_panels
        assert set(panels) == {ME, OTHER}
        assert "you" in text_of(panels[ME])
        assert "16" in text_of(panels[OTHER])


async def test_action_applied_updates_my_hand(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[seat(ME, hands=[["7C", "9S"]], bets=[25])],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        await feed(pilot, transport, action_applied(hand=["7C", "9S", "5D"]))
        assert "21" in text_of(screen(pilot)._seat_panels[ME])


async def test_split_renders_both_hands_with_their_own_bets(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[seat(ME, hands=[["8S", "3C"], ["8H", "9D"]], bets=[25, 25])],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        panel = text_of(screen(pilot)._seat_panels[ME])
        assert panel.count("bet 25") == 2
        assert "11" in panel and "17" in panel


async def test_split_outcomes_are_shown_per_hand(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await feed(
            pilot,
            transport,
            table_state(
                lobby_state="player_turns",
                seats=[seat(ME, hands=[["8S", "3C"], ["8H", "9D"]], bets=[25, 25])],
                dealer_hand=["AC"],
                state_version=6,
            ),
        )
        await feed(
            pilot,
            transport,
            {
                "type": "round_result",
                "results": [
                    {"player_id": ME, "hand_index": 0, "outcome": "loss", "bet": 25,
                     "payout": 0, "net": -25, "balance_after": 975},
                    {"player_id": ME, "hand_index": 1, "outcome": "win", "bet": 25,
                     "payout": 50, "net": 25, "balance_after": 1000},
                ],
                "dealer_hand": ["AC", "KC"],
                "state_version": 9,
            },
        )
        await finish_reveal(pilot)
        panel = text_of(screen(pilot)._seat_panels[ME])
        assert "LOSS" in panel and "WIN" in panel
        body = text_of(q(pilot, "#result-body"))
        assert "hand 1" in body and "hand 2" in body


async def test_escape_leaves_table_and_returns_to_lobby(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        await pilot.press("escape")
        await settle(pilot)
        assert transport.sent_of("leave_table")
        assert isinstance(pilot.app.screen, LobbyScreen)
