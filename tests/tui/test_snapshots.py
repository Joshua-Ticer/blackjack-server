from __future__ import annotations

from collections.abc import Callable

from textual.pilot import Pilot

from app.tui.app import BlackjackApp
from app.tui.widgets.countdown import Countdown
from tests.tui.conftest import do_login, open_table, settle
from tests.tui.fakes import (
    ME,
    OTHER,
    FakeTransport,
    betting_open,
    fake_rest,
    player_turn,
    round_result,
    seat,
    table_state,
)

SIZE = (110, 40)


def make_app() -> tuple[BlackjackApp, FakeTransport]:
    rest, _ = fake_rest()
    transport = FakeTransport()
    return BlackjackApp(rest=rest, transport_factory=lambda: transport), transport


def test_login_screen(snap_compare: Callable[..., bool]) -> None:
    app, _ = make_app()
    assert snap_compare(app, terminal_size=SIZE)


def test_lobby_screen(snap_compare: Callable[..., bool]) -> None:
    app, _ = make_app()

    async def run_before(pilot: Pilot[None]) -> None:
        await do_login(pilot)

    assert snap_compare(app, terminal_size=SIZE, run_before=run_before)


def test_table_betting_open(snap_compare: Callable[..., bool]) -> None:
    app, transport = make_app()

    async def run_before(pilot: Pilot[None]) -> None:
        await open_table(pilot)
        transport.feed(
            table_state(
                lobby_state="betting_open",
                seats=[seat(ME, bets=[25]), seat(OTHER, bets=[10])],
                state_version=3,
            ),
            betting_open(seconds=12),
        )
        await settle(pilot)
        pilot.app.screen.query_one("#countdown", Countdown).freeze(12.0)

    assert snap_compare(app, terminal_size=SIZE, run_before=run_before)


def test_table_your_turn_with_hole_card_hidden(
    snap_compare: Callable[..., bool],
) -> None:
    app, transport = make_app()

    async def run_before(pilot: Pilot[None]) -> None:
        await open_table(pilot)
        transport.feed(
            table_state(
                lobby_state="player_turns",
                seats=[
                    seat(ME, hands=[["AS", "6H"]], bets=[25]),
                    seat(OTHER, hands=[["10D", "9C"]], bets=[10]),
                ],
                dealer_hand=["AC"],
                state_version=6,
            ),
            player_turn(
                legal_actions=["hit", "stand", "double", "surrender"],
                seconds=22,
                state_version=7,
            ),
        )
        await settle(pilot)
        pilot.app.screen.query_one("#countdown", Countdown).freeze(22.0)

    assert snap_compare(app, terminal_size=SIZE, run_before=run_before)


def test_table_round_result(snap_compare: Callable[..., bool]) -> None:
    app, transport = make_app()

    async def run_before(pilot: Pilot[None]) -> None:
        await open_table(pilot)
        transport.feed(
            table_state(
                lobby_state="player_turns",
                seats=[
                    seat(ME, hands=[["AS", "6H", "4D"]], bets=[25]),
                    seat(OTHER, hands=[["10D", "9C"]], bets=[10]),
                ],
                dealer_hand=["AC"],
                state_version=6,
            ),
            round_result(
                outcome="win",
                bet=25,
                payout=50,
                net=25,
                balance_after=1025,
                dealer_hand=["AC", "7C", "9H"],
            ),
        )
        await settle(pilot)
        for _ in range(3):
            pilot.app.screen.reveal_tick()
            await settle(pilot)

    assert snap_compare(app, terminal_size=SIZE, run_before=run_before)


def test_table_dealer_reveal_in_progress(snap_compare: Callable[..., bool]) -> None:
    """Hole card flipped, third card still to come, outcome still withheld."""
    app, transport = make_app()

    async def run_before(pilot: Pilot[None]) -> None:
        await open_table(pilot)
        transport.feed(
            table_state(
                lobby_state="player_turns",
                seats=[
                    seat(ME, hands=[["AS", "6H", "4D"]], bets=[25]),
                    seat(OTHER, hands=[["10D", "9C"]], bets=[10]),
                ],
                dealer_hand=["AC"],
                state_version=6,
            ),
            round_result(
                outcome="win",
                bet=25,
                payout=50,
                net=25,
                balance_after=1025,
                dealer_hand=["AC", "7C", "9H"],
            ),
        )
        await settle(pilot)
        pilot.app.screen.reveal_tick()
        await settle(pilot)

    assert snap_compare(app, terminal_size=SIZE, run_before=run_before)
