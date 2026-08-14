"""Shared fixtures for WebSocket integration tests.

These tests exercise the real gateway end-to-end (auth -> table lookup ->
TableActor -> engine), so a couple of things need help from test-only fixtures
that production code has no reason to expose:

- `starlette.testclient.TestClient` drives the ASGI app on its own event loop in
  a background thread, which is what actually lets a websocket connection and
  the TableActor's `run()` task talk to each other.
- `get_or_create` only takes a `rules`/`seed` on a table's *first* connection,
  and the REST `Table` model has no `seed`/timeout fields -- so determinism and
  fast betting/turn windows for tests come from monkeypatching `get_or_create`
  before the first websocket connects.
"""

import pytest
from starlette.testclient import TestClient

from app.engine.rules import TableRules
from app.main import app
from app.tables.table_manager import TableManager

TABLE_BODY = {"name": "Test Table", "min_bet": 5, "max_bet": 500, "max_seats": 6}


@pytest.fixture
def ws_client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed_table_manager(monkeypatch):
    """Returns a function that forces every `get_or_create` call (regardless of
    the `rules` the gateway builds from the REST table) to use the given rules
    and shoe seed, so a round played through the real WS gateway is fully
    deterministic and doesn't wait on production betting/turn windows.
    """
    real_get_or_create = TableManager.get_or_create

    def _seed(rules: TableRules, seed: int):
        def _patched(self, table_id, _rules, seed_arg=None):
            return real_get_or_create(self, table_id, rules, seed=seed)

        monkeypatch.setattr(TableManager, "get_or_create", _patched)

    return _seed


@pytest.fixture
async def table_and_token(client, signup_and_login):
    """Create a table (as admin) and return (table_id, player_token, player_json)
    for a second, non-admin user ready to connect to it over WS."""
    admin_headers, _ = await signup_and_login(username="admin", admin=True)
    created = await client.post("/tables", json=TABLE_BODY, headers=admin_headers)
    assert created.status_code == 200, created.text
    table_id = created.json()["id"]

    player_headers, player = await signup_and_login(username="player")
    token = player_headers["Authorization"].removeprefix("Bearer ")

    return table_id, token, player
