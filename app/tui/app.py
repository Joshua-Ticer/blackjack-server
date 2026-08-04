from __future__ import annotations

from collections.abc import Callable

from textual.app import App

from app.tui.rest import RestClient, TableInfo, UserInfo
from app.tui.screens.lobby import LobbyScreen
from app.tui.screens.login import LoginScreen
from app.tui.screens.table import TableScreen
from app.tui.session import TableSession
from app.tui.transport import Transport, WebsocketTransport

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class BlackjackApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Blackjack"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        rest: RestClient | None = None,
        transport_factory: Callable[[], Transport] = WebsocketTransport,
    ) -> None:
        super().__init__()
        self.rest = rest or RestClient(base_url)
        self.transport_factory = transport_factory
        self.user: UserInfo | None = None
        self.session: TableSession | None = None

    def get_default_screen(self) -> LoginScreen:
        return LoginScreen()

    async def show_lobby(self) -> None:
        if not any(isinstance(screen, LobbyScreen) for screen in self.screen_stack):
            await self.push_screen(LobbyScreen())

    def open_table(self, info: TableInfo) -> None:
        if self.user is None:
            return
        session = TableSession(self.transport_factory(), me=self.user.id)
        self.session = session
        screen = TableScreen(info, session)
        session.on_update = screen.handle_update
        session.on_closed = screen.handle_closed
        self.push_screen(screen)

    async def back_to_lobby(self) -> None:
        self.session = None
        self.pop_screen()

    def log_out(self) -> None:
        self.user = None
        self.rest.token = None
        self.pop_screen()

    async def action_quit(self) -> None:
        if self.session is not None:
            await self.session.stop()
        await self.rest.aclose()
        self.exit()
