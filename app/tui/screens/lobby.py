from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from app.tui.rest import ApiError, TableInfo

if TYPE_CHECKING:
    from app.tui.app import BlackjackApp


class LobbyScreen(Screen[None]):
    BINDINGS = [
        ("enter", "join", "Join table"),
        ("r", "refresh", "Refresh"),
        ("escape", "log_out", "Log out"),
        ("q", "quit", "Quit"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[TableInfo] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="lobby-body"):
            with Horizontal(id="lobby-bar"):
                yield Static("Tables", id="lobby-title")
                yield Static("", id="lobby-chips")
            yield DataTable(id="tables", cursor_type="row", zebra_stripes=True)
            yield Static("", id="lobby-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tables", DataTable)
        table.add_columns("Table", "Min bet", "Max bet", "Status")
        table.focus()
        self.refresh_tables()

    @property
    def status(self) -> Static:
        return self.query_one("#lobby-status", Static)

    def _set_status(self, message: str, error: bool = False) -> None:
        self.status.update(message)
        self.status.set_class(error, "error")

    def show_chips(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        if app.user is not None:
            self.query_one("#lobby-chips", Static).update(
                f"{app.user.username}   chips {app.user.chip_balance}"
            )

    def action_refresh(self) -> None:
        self.refresh_tables()

    def action_quit(self) -> None:
        self.app.exit()

    def action_log_out(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        app.log_out()

    @work(exclusive=True)
    async def refresh_tables(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        self._set_status("loading tables...")
        try:
            self.tables = await app.rest.tables()
            app.user = await app.rest.me()
        except ApiError as exc:
            self._set_status(str(exc), error=True)
            return

        self.show_chips()
        widget = self.query_one("#tables", DataTable)
        widget.clear()
        for info in self.tables:
            widget.add_row(info.name, str(info.min_bet), str(info.max_bet), info.status)

        if not self.tables:
            self._set_status("no tables available - an admin needs to create one")
        else:
            self._set_status(f"{len(self.tables)} table(s) - enter to join")

    def selected_table(self) -> TableInfo | None:
        widget = self.query_one("#tables", DataTable)
        if not self.tables or widget.cursor_row is None:
            return None
        if 0 <= widget.cursor_row < len(self.tables):
            return self.tables[widget.cursor_row]
        return None

    def action_join(self) -> None:
        self._join_selected()

    @on(DataTable.RowSelected)
    def _row_selected(self) -> None:
        self._join_selected()

    def _join_selected(self) -> None:
        info = self.selected_table()
        if info is None:
            self._set_status("no table selected", error=True)
            return
        app: BlackjackApp = self.app  # type: ignore[assignment]
        app.open_table(info)
