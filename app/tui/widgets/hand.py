from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from app.tui.cards import (
    CARD_HEIGHT,
    card_lines,
    face_down_lines,
    is_red,
    total_label,
)

FACE_BG = "#f4f1ea"
RED_FG = "#b3121f"
BLACK_FG = "#1b1b1b"
BACK_BG = "#1d3557"
BACK_FG = "#4d7ab5"

STYLE_RED = f"bold {RED_FG} on {FACE_BG}"
STYLE_BLACK = f"bold {BLACK_FG} on {FACE_BG}"
STYLE_BACK = f"{BACK_FG} on {BACK_BG}"

EMPTY_SLOT = "  --  "


def hand_text(cards: list[str], face_down: int = 0, gap: str = " ") -> Text:
    blocks: list[tuple[list[str], str]] = []
    for card in cards:
        blocks.append((card_lines(card), STYLE_RED if is_red(card) else STYLE_BLACK))
    for _ in range(face_down):
        blocks.append((face_down_lines(), STYLE_BACK))

    if not blocks:
        return Text(EMPTY_SLOT, style="dim")

    rows: list[Text] = []
    for row in range(CARD_HEIGHT):
        line = Text()
        for index, (lines, style) in enumerate(blocks):
            if index:
                line.append(gap)
            line.append(lines[row], style=style)
        rows.append(line)
    return Text("\n").join(rows)


class HandDisplay(Static):
    DEFAULT_CSS = """
    HandDisplay {
        height: auto;
        width: auto;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__("", **kwargs)  # type: ignore[arg-type]
        self._cards: list[str] = []
        self._face_down = 0

    def show(self, cards: list[str], face_down: int = 0) -> None:
        self._cards = list(cards)
        self._face_down = face_down
        self.update(hand_text(self._cards, face_down))

    @property
    def label(self) -> str:
        if self._face_down:
            return "?"
        return total_label(self._cards)
