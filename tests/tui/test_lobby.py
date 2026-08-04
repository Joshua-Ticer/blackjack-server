from __future__ import annotations

from textual.widgets import DataTable

from app.tui.app import BlackjackApp
from app.tui.screens.lobby import LobbyScreen
from app.tui.screens.table import TableScreen
from tests.tui.conftest import do_login, q, settle, text_of
from tests.tui.fakes import TABLE_ID, FakeBackend, FakeTransport


async def test_lobby_lists_tables_with_limits(bj_app: BlackjackApp):
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        table = q(pilot, "#tables", DataTable)
        assert table.row_count == 1
        row = table.get_row_at(0)
        assert row[0] == "High Roller"
        assert row[1] == "5"
        assert row[2] == "500"
        assert row[3] == "open"


async def test_lobby_shows_chip_balance(bj_app: BlackjackApp, backend: FakeBackend):
    backend.chip_balance = 750
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        assert "750" in text_of(q(pilot, "#lobby-chips"))


async def test_empty_lobby_explains_why(bj_app: BlackjackApp, backend: FakeBackend):
    backend.tables = []
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        assert "no tables available" in text_of(q(pilot, "#lobby-status"))


async def test_enter_joins_selected_table(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(pilot.app.screen, TableScreen)
        assert transport.connected
        assert TABLE_ID in transport.urls[0]


async def test_join_sends_join_table_then_sit(bj_app: BlackjackApp, transport: FakeTransport):
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        await pilot.press("enter")
        await settle(pilot)
        kinds = [m["type"] for m in transport.sent]
        assert kinds[:2] == ["join_table", "sit"]


async def test_refresh_reloads_tables(bj_app: BlackjackApp, backend: FakeBackend):
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        backend.tables.append(
            {"id": "x", "name": "Low Stakes", "min_bet": 1, "max_bet": 20, "status": "open"}
        )
        await pilot.press("r")
        await settle(pilot)
        assert q(pilot, "#tables", DataTable).row_count == 2


async def test_escape_logs_out_back_to_login(bj_app: BlackjackApp):
    from app.tui.screens.login import LoginScreen

    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        await pilot.press("escape")
        await settle(pilot)
        assert isinstance(pilot.app.screen, LoginScreen)
        assert bj_app.user is None
        assert bj_app.rest.token is None


async def test_q_quits_from_the_lobby(bj_app: BlackjackApp):
    quit_calls: list[bool] = []

    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        assert isinstance(pilot.app.screen, LobbyScreen)
        bj_app.exit = lambda *a, **k: quit_calls.append(True)  # type: ignore[method-assign]
        await pilot.press("q")
        await settle(pilot)
        assert quit_calls == [True]


async def test_join_with_no_tables_stays_in_lobby(
    bj_app: BlackjackApp, backend: FakeBackend, transport: FakeTransport
):
    backend.tables = []
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert isinstance(pilot.app.screen, LobbyScreen)
        assert transport.connect_count == 0


async def test_join_without_a_selection_reports_error(bj_app: BlackjackApp, backend: FakeBackend):
    backend.tables = []
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        pilot.app.screen.action_join()
        await settle(pilot)
        assert "no table selected" in text_of(q(pilot, "#lobby-status"))
