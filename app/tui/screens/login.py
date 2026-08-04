from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from app.tui.rest import ApiError

if TYPE_CHECKING:
    from app.tui.app import BlackjackApp


class LoginScreen(Screen[None]):
    BINDINGS = [
        ("ctrl+l", "submit_login", "Log in"),
        ("ctrl+n", "submit_signup", "Sign up"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                with Vertical(id="login-card"):
                    yield Static("BLACKJACK", id="login-title")
                    yield Static("sign in to take a seat", id="login-subtitle")
                    yield Input(placeholder="username", id="username")
                    yield Input(placeholder="password", password=True, id="password")
                    with Center():
                        yield Button("Log in", variant="primary", id="login")
                        yield Button("Sign up", variant="default", id="signup")
                    yield Static("", id="login-status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#username", Input).focus()

    @property
    def status(self) -> Static:
        return self.query_one("#login-status", Static)

    def _credentials(self) -> tuple[str, str]:
        return (
            self.query_one("#username", Input).value.strip(),
            self.query_one("#password", Input).value,
        )

    def action_quit(self) -> None:
        self.app.exit()

    def action_submit_login(self) -> None:
        self.authenticate(signup=False)

    def action_submit_signup(self) -> None:
        self.authenticate(signup=True)

    @on(Button.Pressed, "#login")
    def _login_pressed(self) -> None:
        self.authenticate(signup=False)

    @on(Button.Pressed, "#signup")
    def _signup_pressed(self) -> None:
        self.authenticate(signup=True)

    @on(Input.Submitted)
    def _submitted(self) -> None:
        self.authenticate(signup=False)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status.update(message)
        self.status.set_class(error, "error")
        self.status.set_class(not error, "info")

    @work(exclusive=True)
    async def authenticate(self, signup: bool) -> None:
        username, password = self._credentials()
        if not username or not password:
            self._set_status("username and password are required", error=True)
            return

        app: BlackjackApp = self.app  # type: ignore[assignment]
        self._set_status("signing up..." if signup else "logging in...")

        try:
            if signup:
                await app.rest.signup(username, password)
            await app.rest.login(username, password)
            user = await app.rest.me()
        except ApiError as exc:
            self._set_status(str(exc), error=True)
            return

        app.user = user
        await app.show_lobby()
