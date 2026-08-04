from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from rich.text import Text
from textual.widgets import Static

TICK_SECONDS = 0.25
BAR_WIDTH = 16


class Countdown(Static):
    DEFAULT_CSS = """
    Countdown {
        height: 1;
        width: auto;
        content-align: left middle;
    }
    """

    def __init__(self, now: Callable[[], datetime] | None = None, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._now = now or datetime.now
        self._deadline: datetime | None = None
        self._label = ""
        self._window = 1.0

    def on_mount(self) -> None:
        self.set_interval(TICK_SECONDS, self.refresh_display)

    def start(self, deadline: datetime | None, label: str) -> None:
        self._deadline = deadline
        self._label = label
        remaining = self.remaining()
        self._window = max(remaining, 1.0)
        self.refresh_display()

    def freeze(self, remaining: float) -> None:
        if self._deadline is None:
            return
        fixed = self._deadline - timedelta(seconds=remaining)
        self._now = lambda: fixed
        self.refresh_display()

    def clear(self) -> None:
        self._deadline = None
        self._label = ""
        self.update("")

    def remaining(self) -> float:
        if self._deadline is None:
            return 0.0
        return max(0.0, (self._deadline - self._now()).total_seconds())

    def refresh_display(self) -> None:
        if self._deadline is None:
            self.update("")
            return

        remaining = self.remaining()
        fraction = min(1.0, remaining / self._window) if self._window else 0.0
        filled = int(round(fraction * BAR_WIDTH))

        if remaining <= 5:
            style = "bold #d62828"
        elif remaining <= 10:
            style = "bold #e08e2b"
        else:
            style = "bold #2a9d8f"

        text = Text()
        text.append(f"{self._label} ", style="bold")
        text.append("█" * filled, style=style)
        text.append("░" * (BAR_WIDTH - filled), style="dim")
        text.append(f" {remaining:4.1f}s", style=style)
        self.update(text)
