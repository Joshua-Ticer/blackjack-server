from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import App, ComposeResult

from app.tui.app import BlackjackApp
from app.tui.widgets.countdown import Countdown
from tests.tui.conftest import open_table, q, settle, text_of
from tests.tui.fakes import FakeTransport, betting_open, player_turn, table_state


class ClockApp(App[None]):
    def __init__(self, now: datetime) -> None:
        super().__init__()
        self.fixed = now

    def compose(self) -> ComposeResult:
        yield Countdown(now=lambda: self.fixed, id="cd")


async def test_countdown_renders_remaining_seconds():
    start = datetime(2026, 8, 4, 12, 0, 0)
    app = ClockApp(start)
    async with app.run_test() as pilot:
        widget = pilot.app.query_one("#cd", Countdown)
        widget.start(start + timedelta(seconds=12), "betting closes")
        await pilot.pause()
        rendered = text_of(widget)
        assert "betting closes" in rendered
        assert "12.0s" in rendered


async def test_countdown_counts_down_as_the_clock_advances():
    start = datetime(2026, 8, 4, 12, 0, 0)
    app = ClockApp(start)
    async with app.run_test() as pilot:
        widget = pilot.app.query_one("#cd", Countdown)
        widget.start(start + timedelta(seconds=15), "your turn")
        await pilot.pause()
        assert "15.0s" in text_of(widget)

        app.fixed = start + timedelta(seconds=10)
        widget.refresh_display()
        await pilot.pause()
        assert " 5.0s" in text_of(widget)


async def test_countdown_floors_at_zero_and_never_goes_negative():
    start = datetime(2026, 8, 4, 12, 0, 0)
    app = ClockApp(start)
    async with app.run_test() as pilot:
        widget = pilot.app.query_one("#cd", Countdown)
        widget.start(start + timedelta(seconds=5), "your turn")
        app.fixed = start + timedelta(seconds=30)
        widget.refresh_display()
        await pilot.pause()
        assert widget.remaining() == 0.0
        assert " 0.0s" in text_of(widget)


async def test_countdown_bar_drains():
    start = datetime(2026, 8, 4, 12, 0, 0)
    app = ClockApp(start)
    async with app.run_test() as pilot:
        widget = pilot.app.query_one("#cd", Countdown)
        widget.start(start + timedelta(seconds=20), "betting closes")
        await pilot.pause()
        full = text_of(widget).count("█")

        app.fixed = start + timedelta(seconds=15)
        widget.refresh_display()
        await pilot.pause()
        assert text_of(widget).count("█") < full


async def test_clear_blanks_the_countdown():
    start = datetime(2026, 8, 4, 12, 0, 0)
    app = ClockApp(start)
    async with app.run_test() as pilot:
        widget = pilot.app.query_one("#cd", Countdown)
        widget.start(start + timedelta(seconds=10), "your turn")
        widget.clear()
        await pilot.pause()
        assert text_of(widget) == ""


# --- wiring into the table screen ------------------------------------------


async def test_betting_deadline_drives_the_countdown(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        transport.feed(betting_open(seconds=15))
        await settle(pilot)
        assert "betting closes" in text_of(q(pilot, "#countdown"))


async def test_turn_deadline_replaces_betting_countdown(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        transport.feed(betting_open(seconds=15))
        await settle(pilot)
        transport.feed(player_turn(seconds=30, state_version=9))
        await settle(pilot)
        assert "your turn" in text_of(q(pilot, "#countdown"))


async def test_countdown_clears_when_no_deadline_is_active(
    bj_app: BlackjackApp, transport: FakeTransport
):
    async with bj_app.run_test() as pilot:
        await open_table(pilot)
        transport.feed(table_state(lobby_state="idle", state_version=4))
        await settle(pilot)
        assert text_of(q(pilot, "#countdown")) == ""
