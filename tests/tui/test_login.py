from __future__ import annotations

from textual.widgets import Input, Static

from app.tui.app import BlackjackApp
from app.tui.screens.lobby import LobbyScreen
from app.tui.screens.login import LoginScreen
from tests.tui.conftest import do_login, q, settle, text_of
from tests.tui.fakes import FakeBackend


async def test_login_screen_starts_focused_on_username(bj_app: BlackjackApp):
    async with bj_app.run_test() as pilot:
        assert isinstance(pilot.app.screen, LoginScreen)
        assert pilot.app.focused is q(pilot, "#username", Input)


async def test_signup_then_login_reaches_lobby(
    bj_app: BlackjackApp, backend: FakeBackend
):
    async with bj_app.run_test() as pilot:
        await do_login(pilot, "player", "pw")
        assert isinstance(pilot.app.screen, LobbyScreen)
        assert bj_app.user is not None
        assert bj_app.user.username == "player"
        assert bj_app.rest.token == "test-token"


async def test_existing_user_can_log_in_without_signup(
    bj_app: BlackjackApp, backend: FakeBackend
):
    backend.users["player"] = "pw"
    async with bj_app.run_test() as pilot:
        q(pilot, "#username", Input).value = "player"
        q(pilot, "#password", Input).value = "pw"
        await pilot.press("ctrl+l")
        await settle(pilot)
        assert isinstance(pilot.app.screen, LobbyScreen)


async def test_blank_credentials_are_rejected_without_a_request(bj_app: BlackjackApp):
    async with bj_app.run_test() as pilot:
        await pilot.press("ctrl+l")
        await settle(pilot)
        status = text_of(q(pilot, "#login-status", Static))
        assert "required" in status
        assert isinstance(pilot.app.screen, LoginScreen)


async def test_wrong_password_shows_server_detail(
    bj_app: BlackjackApp, backend: FakeBackend
):
    backend.users["player"] = "correct"
    async with bj_app.run_test() as pilot:
        q(pilot, "#username", Input).value = "player"
        q(pilot, "#password", Input).value = "wrong"
        await pilot.press("ctrl+l")
        await settle(pilot)
        status = text_of(q(pilot, "#login-status", Static))
        assert "Incorrect username or password" in status
        assert isinstance(pilot.app.screen, LoginScreen)


async def test_duplicate_signup_shows_error(bj_app: BlackjackApp, backend: FakeBackend):
    backend.users["player"] = "pw"
    async with bj_app.run_test() as pilot:
        await do_login(pilot, "player", "pw")
        status = text_of(q(pilot, "#login-status", Static))
        assert "already taken" in status


async def test_token_is_held_in_memory_only(bj_app: BlackjackApp):
    async with bj_app.run_test() as pilot:
        await do_login(pilot)
        assert bj_app.rest.token == "test-token"
        assert "test-token" in bj_app.rest.ws_url("some-table")
