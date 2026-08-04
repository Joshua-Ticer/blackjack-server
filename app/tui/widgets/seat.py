from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from app.tui.cards import total_label
from app.tui.protocol import SeatState
from app.tui.widgets.hand import hand_text

OUTCOME_STYLES = {
    "win": "bold #2a9d8f",
    "blackjack": "bold #e9c46a",
    "push": "bold #8d99ae",
    "loss": "bold #d62828",
    "bust": "bold #d62828",
    "surrender": "bold #8d99ae",
}


def short_id(player_id: str) -> str:
    return player_id.split("-")[0]


def seat_label(seat: SeatState, me: str) -> str:
    return "you" if seat.player_id == me else short_id(seat.player_id)


class SeatPanel(Static):
    DEFAULT_CSS = """
    SeatPanel {
        height: auto;
        width: auto;
        padding: 0 1;
        margin-right: 2;
        border: round $panel-lighten-2;
    }
    SeatPanel.is-me {
        border: round #e9c46a;
    }
    SeatPanel.is-active {
        border: round #2a9d8f;
        background: $boost;
    }
    """

    def __init__(self, seat: SeatState, me: str, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self.seat = seat
        self.me = me
        self.active_hand: int | None = None
        self.outcomes: dict[int, str] = {}

    def on_mount(self) -> None:
        self.render_seat()

    def set_state(
        self,
        seat: SeatState,
        active_hand: int | None = None,
        outcomes: dict[int, str] | None = None,
    ) -> None:
        self.seat = seat
        self.active_hand = active_hand
        self.outcomes = outcomes or {}
        self.render_seat()

    @property
    def is_me(self) -> bool:
        return self.seat.player_id == self.me

    def render_seat(self) -> None:
        self.set_class(self.is_me, "is-me")
        self.set_class(self.active_hand is not None, "is-active")

        header = Text()
        header.append(
            seat_label(self.seat, self.me),
            style="bold #e9c46a" if self.is_me else "bold",
        )
        bet = self.seat.bets[0] if self.seat.bets else 0
        if bet and len(self.seat.hands) < 2:
            header.append(f"   bet {bet}", style="#8d99ae")

        body = [header]
        if not self.seat.hands:
            body.append(Text("waiting", style="dim"))
        for index, hand in enumerate(self.seat.hands):
            line = Text()
            marker = "▸ " if index == self.active_hand else "  "
            line.append(marker, style="bold #2a9d8f")
            line.append(total_label(hand), style="bold")
            if len(self.seat.hands) > 1 and index < len(self.seat.bets):
                line.append(f"  bet {self.seat.bets[index]}", style="#8d99ae")
            outcome = self.outcomes.get(index)
            if outcome:
                line.append(f"  {outcome.upper()}", style=OUTCOME_STYLES.get(outcome, "bold"))
            body.append(hand_text(hand))
            body.append(line)

        self.update(Text("\n").join(body))
