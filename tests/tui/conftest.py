from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from textual.pilot import Pilot
from textual.widgets import Input

from app.tui.app import BlackjackApp
from tests.tui.fakes import FakeBackend, FakeTransport, fake_rest


@pytest.fixture(autouse=True)
async def _isolate_database() -> AsyncIterator[None]:
    yield


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
async def bj_app(
    backend: FakeBackend, transport: FakeTransport
) -> AsyncIterator[BlackjackApp]:
    rest, _ = fake_rest(backend)
    app = BlackjackApp(rest=rest, transport_factory=lambda: transport)
    yield app
    await rest.aclose()


def q(pilot: Pilot[None], *args: object) -> object:
    return pilot.app.screen.query_one(*args)  # type: ignore[arg-type]


def is_on_screen(pilot: Pilot[None], selector: str) -> bool:
    """True only if the widget is displayed AND fits inside the terminal viewport.

    `.display` alone is not enough: an overflowing container happily lays a widget
    out past the bottom edge, where the user cannot see or reach it.
    """
    widget = pilot.app.screen.query_one(selector)
    if not widget.display:
        return False
    region = widget.region
    return (
        region.height > 0
        and region.y >= 0
        and region.y + region.height <= pilot.app.size.height
    )


def text_of(widget: object) -> str:
    return str(widget.render())  # type: ignore[attr-defined]


def screen_text(pilot: Pilot[None], selector: str) -> str:
    return text_of(q(pilot, selector))


async def settle(pilot: Pilot[None], count: int = 3) -> None:
    for _ in range(count):
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()


async def do_login(
    pilot: Pilot[None], username: str = "player", password: str = "pw"
) -> None:
    q(pilot, "#username", Input).value = username
    q(pilot, "#password", Input).value = password
    await pilot.press("ctrl+n")
    await settle(pilot)


async def open_table(pilot: Pilot[None]) -> None:
    await do_login(pilot)
    await pilot.press("enter")
    await settle(pilot)
