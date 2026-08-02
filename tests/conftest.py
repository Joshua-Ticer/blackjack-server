"""Shared pytest fixtures.

TODO:
- a seeded-shoe fixture for deterministic engine tests
- a test-Postgres fixture (docker-compose test profile or pytest-postgresql)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import deps
from app.api.routes import tables as tables_routes
from app.main import app
from app.tables.table_manager import table_manager


def _clear_table_manager():
    """Cancel every live TableActor task and drop it from the registry.

    Actors created during a WS test may be running on a different event loop
    (e.g. starlette's TestClient drives its own loop in a background thread),
    so `task.cancel()` must be scheduled via that task's own loop rather than
    called directly from whatever loop this fixture happens to run on.
    """
    for task in list(table_manager._tasks.values()):
        try:
            task.get_loop().call_soon_threadsafe(task.cancel)
        except RuntimeError:
            # loop already closed -- nothing left to schedule cancellation on
            task.cancel()
    table_manager._actors.clear()
    table_manager._tasks.clear()


@pytest.fixture(autouse=True)
def _reset_in_memory_stores():
    """Phase 2 persistence is in-memory module state; isolate tests from each other."""
    deps._users_by_id.clear()
    deps._users_by_username.clear()
    tables_routes._tables.clear()
    _clear_table_manager()
    yield
    deps._users_by_id.clear()
    deps._users_by_username.clear()
    tables_routes._tables.clear()
    _clear_table_manager()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def signup_and_login(client: AsyncClient):
    """Create a user and return (headers, user_json) with a valid bearer token."""

    async def _make(username: str = "josh", password: str = "hunter22", admin: bool = False):
        signup = await client.post(
            "/auth/signup", json={"username": username, "password": password}
        )
        assert signup.status_code == 200, signup.text
        user = signup.json()

        if admin:
            deps._users_by_id[user["id"]].is_admin = True

        login = await client.post(
            "/auth/login", data={"username": username, "password": password}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, user

    return _make
