from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, Input, Static

from app.tui.cards import hand_total, total_label
from app.tui.protocol import SeatState
from app.tui.rest import TableInfo
from app.tui.session import TableSession
from app.tui.transport import TransportClosed, close_reason
from app.tui.widgets.countdown import Countdown
from app.tui.widgets.hand import HandDisplay
from app.tui.widgets.seat import OUTCOME_STYLES, SeatPanel

if TYPE_CHECKING:
    from app.tui.app import BlackjackApp

ACTIONS: list[tuple[str, str, str]] = [
    ("hit", "h", "Hit"),
    ("stand", "s", "Stand"),
    ("double", "d", "Double"),
    ("split", "p", "Split"),
    ("surrender", "u", "Surrender"),
]

def net_style(net: int) -> str:
    if net > 0:
        return "bold #2a9d8f"
    if net < 0:
        return "bold #d62828"
    return "bold #8d99ae"


LOBBY_LABELS = {
    "idle": "Waiting for players",
    "betting_open": "Betting open",
    "betting_closed": "Betting closed",
    "player_turns": "Player turns",
    "dealer_turn": "Dealer playing",
    "settlement": "Round complete - next hand shortly",
}


class TableScreen(Screen[None]):
    BINDINGS = [
        ("h", "act('hit')", "Hit"),
        ("s", "act('stand')", "Stand"),
        ("d", "act('double')", "Double"),
        ("p", "act('split')", "Split"),
        ("u", "act('surrender')", "Surrender"),
        ("b", "focus_bet", "Bet"),
        ("t", "sit", "Sit"),
        ("ctrl+r", "reconnect", "Reconnect"),
        ("escape", "leave", "Leave table"),
        ("ctrl+q", "quit", "Quit"),
    ]

    REVEAL_SECONDS = 1.0

    def __init__(self, info: TableInfo, session: TableSession) -> None:
        super().__init__()
        self.info = info
        self.session = session
        self.model = session.model
        self._seat_panels: dict[str, SeatPanel] = {}
        self._reveal_timer: Timer | None = None
        self._last_bet = 0
        self._bet_prompted = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="table-body"):
            with VerticalScroll(id="felt"):
                with Vertical(id="dealer-area"):
                    yield Static("DEALER", classes="area-title")
                    yield HandDisplay(id="dealer-hand")
                    yield Static("", id="dealer-total")
                yield Static("", id="table-divider")
                yield Static("SEATS", classes="area-title")
                yield Horizontal(id="seats")
                with Vertical(id="result-panel"):
                    yield Static("", id="result-body")
            with Horizontal(id="status-bar"):
                yield Static("", id="lobby-state")
                yield Countdown(id="countdown")
            with Horizontal(id="bet-bar"):
                yield Static("Bet", id="bet-label")
                yield Input(placeholder="amount", id="bet-input", type="integer")
                yield Static("", id="bet-hint")
            with Horizontal(id="action-bar"):
                for action, key, label in ACTIONS:
                    yield Button(f"{label} \\[{key}]", id=f"act-{action}", disabled=True)
            yield Static("", id="table-error")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.info.name
        self.query_one("#result-panel").display = False
        self.connect()

    # -- connection ---------------------------------------------------------

    @work(exclusive=True)
    async def connect(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        self._set_error("")
        self._set_lobby_text("connecting...")
        try:
            await self.session.connect(app.rest.ws_url(self.info.id))
            await self.session.join()
            await self.session.sit()
        except TransportClosed as closed:
            self._fail(close_reason(closed.code))
            return
        except Exception as exc:
            self._fail(str(exc))
            return
        self.refresh_view()

    def on_unmount(self) -> None:
        self.stop_dealer_reveal()

    def _fail(self, message: str) -> None:
        self._set_error(message)
        self._set_lobby_text("disconnected")

    async def handle_update(self, message: dict[str, Any]) -> None:
        if message.get("type") == "round_result" and self.model.reveal_pending():
            self.start_dealer_reveal()
        self.refresh_view()

    async def handle_closed(self, closed: TransportClosed) -> None:
        self._fail(f"{close_reason(closed.code)} - ctrl+r to reconnect")

    def start_dealer_reveal(self) -> None:
        self.stop_dealer_reveal()
        self._reveal_timer = self.set_interval(self.REVEAL_SECONDS, self.reveal_tick)

    def stop_dealer_reveal(self) -> None:
        if self._reveal_timer is not None:
            self._reveal_timer.stop()
            self._reveal_timer = None

    def reveal_tick(self) -> None:
        if self.model.advance_dealer_reveal():
            self.stop_dealer_reveal()
            self._apply_settlement()
        self.refresh_view()

    def _apply_settlement(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        for result in self.model.my_results():
            if app.user is not None:
                app.user.chip_balance = result.balance_after
        self._render_header()

    def action_quit(self) -> None:
        self.stop_dealer_reveal()
        self.app.exit()

    def action_reconnect(self) -> None:
        self.reconnect()

    @work(exclusive=True)
    async def reconnect(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        self._set_error("reconnecting...")
        try:
            await self.session.reconnect(app.rest.ws_url(self.info.id))
        except TransportClosed as closed:
            self._fail(close_reason(closed.code))
            return
        self._set_error("")
        self.refresh_view()

    # -- intents ------------------------------------------------------------

    def action_sit(self) -> None:
        self.send_sit()

    @work
    async def send_sit(self) -> None:
        await self.session.sit()

    def action_focus_bet(self) -> None:
        if self.model.betting_is_open():
            self.query_one("#bet-input", Input).focus()

    @on(Input.Submitted, "#bet-input")
    def _bet_submitted(self) -> None:
        self.submit_bet()

    @work
    async def submit_bet(self) -> None:
        widget = self.query_one("#bet-input", Input)
        raw = widget.value.strip()
        if not self.model.betting_is_open():
            self._set_error("betting is not open")
            return
        amount = int(raw) if raw else self.suggested_bet()
        if amount <= 0:
            return
        betting = self.model.betting
        if betting is not None and not (betting.min_bet <= amount <= betting.max_bet):
            self._set_error(f"bet must be between {betting.min_bet} and {betting.max_bet}")
            return
        self._set_error("")
        self._last_bet = amount
        await self.session.place_bet(amount)
        widget.value = ""
        self.set_focus(None)

    def action_act(self, action: str) -> None:
        if not self.model.can(action):
            return
        self.send_action(action)

    @work
    async def send_action(self, action: str) -> None:
        await self.session.act(action)
        self.refresh_view()

    @on(Button.Pressed)
    def _action_button(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("act-"):
            self.action_act(button_id.removeprefix("act-"))

    def action_leave(self) -> None:
        self.leave()

    @work(exclusive=True)
    async def leave(self) -> None:
        try:
            await self.session.leave()
            await self.session.stop()
        except TransportClosed:
            pass
        app: BlackjackApp = self.app  # type: ignore[assignment]
        await app.back_to_lobby()

    # -- rendering ----------------------------------------------------------

    def _set_error(self, message: str) -> None:
        widget = self.query_one("#table-error", Static)
        widget.update(message)
        widget.set_class(bool(message), "error")

    def _set_lobby_text(self, message: str) -> None:
        self.query_one("#lobby-state", Static).update(message)

    def _render_header(self) -> None:
        app: BlackjackApp = self.app  # type: ignore[assignment]
        if app.user is not None:
            self.sub_title = f"{self.info.name}   chips {app.user.chip_balance}"

    def refresh_view(self) -> None:
        if not self.is_mounted:
            return
        self._render_header()
        self._render_dealer()
        self._render_seats()
        self._render_status()
        self._render_bet_bar()
        self._render_actions()
        self._render_result()
        if self.model.error:
            self._set_error(self.model.error)

    def _render_dealer(self) -> None:
        hand = self.query_one("#dealer-hand", HandDisplay)
        cards = self.model.visible_dealer_cards()
        face_down = self.model.dealer_face_down() if cards else 0
        hand.show(cards, face_down)

        total = self.query_one("#dealer-total", Static)
        if not cards:
            total.update("")
        elif self.model.dealer_revealed:
            total.update(Text(total_label(cards), style="bold"))
        else:
            total.update(Text(f"showing {hand_total(cards)}", style="dim"))

    def _outcomes_for(self, player_id: str) -> dict[int, str]:
        if not self.model.settlement_visible:
            return {}
        return {
            r.hand_index: r.outcome
            for r in (self.model.results or [])
            if r.player_id == player_id
        }

    def _render_seats(self) -> None:
        container = self.query_one("#seats", Horizontal)
        seats = self.model.seats
        present = {seat.player_id for seat in seats}

        for player_id in list(self._seat_panels):
            if player_id not in present:
                self._seat_panels.pop(player_id).remove()

        for seat in seats:
            panel = self._seat_panels.get(seat.player_id)
            if panel is None:
                panel = SeatPanel(seat, self.model.me)
                self._seat_panels[seat.player_id] = panel
                container.mount(panel)
            active = self._active_hand_for(seat)
            panel.set_state(seat, active, self._outcomes_for(seat.player_id))

    def _active_hand_for(self, seat: SeatState) -> int | None:
        turn = self.model.turn
        if turn is None or seat.player_id != self.model.me:
            return None
        return turn.hand_index

    def _render_status(self) -> None:
        state = self.model.lobby_state
        self._set_lobby_text(LOBBY_LABELS.get(state, state))

        countdown = self.query_one("#countdown", Countdown)
        deadline = self.model.active_deadline()
        if deadline is None:
            countdown.clear()
        elif self.model.turn is not None:
            countdown.start(deadline, "your turn")
        else:
            countdown.start(deadline, "betting closes")

    def _render_bet_bar(self) -> None:
        bar = self.query_one("#bet-bar")
        widget = self.query_one("#bet-input", Input)
        open_now = self.model.betting_is_open()
        bar.display = open_now
        if not open_now:
            self._bet_prompted = False
            if self.focused is widget:
                self.set_focus(None)
            return

        betting = self.model.betting
        hint = self.query_one("#bet-hint", Static)

        if not self._bet_prompted and not self.model.my_bet:
            self._bet_prompted = True
            widget.focus()

        if self.model.my_bet:
            hint.update(
                Text(f"bet {self.model.my_bet} placed - waiting for the deal", style="bold #2a9d8f")
            )
        elif betting is not None:
            hint.update(
                Text(
                    f"enter to bet {self.suggested_bet()}   "
                    f"(min {betting.min_bet} / max {betting.max_bet})",
                    style="bold #e9c46a",
                )
            )

    def suggested_bet(self) -> int:
        betting = self.model.betting
        if betting is None:
            return self._last_bet
        fallback = self._last_bet or betting.min_bet
        return max(betting.min_bet, min(fallback, betting.max_bet))

    def _render_actions(self) -> None:
        for action, _, _ in ACTIONS:
            self.query_one(f"#act-{action}", Button).disabled = not self.model.can(action)

    def _render_result(self) -> None:
        panel = self.query_one("#result-panel")
        results = self.model.visible_results()
        if not results:
            panel.display = False
            return

        panel.display = True
        body = Text()
        for index, result in enumerate(results):
            if index:
                body.append("\n")
            body.append(f"hand {result.hand_index + 1}  ", style="dim")
            body.append(
                result.outcome.upper(), style=OUTCOME_STYLES.get(result.outcome, "bold")
            )
            body.append(f"   bet {result.bet}   payout {result.payout}   ")
            body.append(f"{result.net:+d}", style=net_style(result.net))
            body.append(f"   chips {result.balance_after}", style="bold")
        self.query_one("#result-body", Static).update(body)
