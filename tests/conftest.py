"""Shared pytest fixtures.

Tests run against a dedicated `<dbname>_test` database, created on demand, so a test
run can never truncate your development data. Override with TEST_DATABASE_URL.

Isolation is per-test TRUNCATE rather than transaction rollback. Rollback isolation
works by overriding the `get_session` dependency, but `TableActor`,
`settlement_service`, and the WS gateway build sessions from `SessionLocal` directly
and commit on their own connections -- dependency overrides never reach them, so
their writes would survive a rollback. Truncation doesn't care who committed.
"""

# E402 is deliberate throughout: `settings` must be repointed at the test database
# *before* app.db.session is imported, because that module builds the engine at import
# time. Sorting these imports to the top would build an engine against the dev DB.
# ruff: noqa: E402

import asyncio
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import pytest

# --- Point the app at the test database BEFORE app.db.session builds its engine. ---
# app.config only holds settings (no engine), so importing it first is safe; mutating
# `settings` here is what makes the engine, SessionLocal, and every module that
# captured SessionLocal at import time all resolve to the test DB.
from app.config import settings


def _derive_test_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"{parts.path.rstrip('/')}_test"))


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _derive_test_url(
    settings.database_url
)

settings.database_url = TEST_DATABASE_URL
settings.app_env = "test"  # -> NullPool + echo off, see app/db/session.py

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.main import app

# ledger/round/table are imported for their side effect: registering every model on
# Base.metadata, so create_all and _TABLES below see all six tables. app.main happens
# to pull them in transitively today, but that's incidental -- a model no route
# references would otherwise be silently missing from the test schema.
from app.models import ledger  # noqa: F401
from app.models import round as round_models  # noqa: F401
from app.models import table as table_models  # noqa: F401
from app.models.user import User
from app.tables.table_manager import table_manager


def _sync_dsn(url: str) -> str:
    """asyncpg's own DSN form -- no SQLAlchemy dialect prefix."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _throwaway_engine():
    """A short-lived, unpooled engine for test-harness bookkeeping.

    Deliberately not the app's shared engine: WS tests commit from starlette's
    TestClient loop, and handing a pooled connection across event loops is exactly
    the failure NullPool exists to avoid. Always `await eng.dispose()`.
    """
    return create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


async def _ensure_test_database() -> None:
    """CREATE DATABASE <name>_test if it isn't there yet (needs the `postgres` db)."""
    import asyncpg

    parts = urlsplit(TEST_DATABASE_URL)
    dbname = parts.path.lstrip("/")
    admin_dsn = _sync_dsn(urlunsplit(parts._replace(path="/postgres")))

    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


async def _create_schema() -> None:
    eng = _throwaway_engine()
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await eng.dispose()


# Runs once, at collection time, before any test needs a connection.
asyncio.run(_ensure_test_database())
asyncio.run(_create_schema())

_TABLES = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)


async def _truncate_all() -> None:
    """Wipe every table."""
    eng = _throwaway_engine()
    try:
        async with eng.begin() as conn:
            await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    finally:
        await eng.dispose()


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
async def _isolate_database():
    """Every test starts against an empty database and no live actors."""
    _clear_table_manager()
    await _truncate_all()
    yield
    _clear_table_manager()
    await _truncate_all()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def seed_history():
    """Insert two settled rounds + two ledger entries for `user_id`.

    `started_at`/`created_at` are set explicitly rather than left to
    `server_default=func.now()`: rows inserted in one transaction would share an
    identical timestamp, making the routes' `ORDER BY ... DESC` non-deterministic
    and the pagination assertions flaky.
    """

    async def _seed(user_id: str) -> dict:
        from app.models.ledger import LedgerEntry
        from app.models.round import GameSession, Participation
        from app.models.round import Round as RoundModel
        from app.models.table import Table

        base = datetime(2026, 1, 1, 12, 0, 0)
        eng = _throwaway_engine()
        try:
            sm = async_sessionmaker(bind=eng, expire_on_commit=False)
            async with sm() as s:
                async with s.begin():
                    tbl = Table(name="History Table", min_bet=5, max_bet=500, max_seats=6)
                    s.add(tbl)
                    await s.flush()

                    gs = GameSession(table_id=tbl.id)
                    s.add(gs)
                    await s.flush()

                    round_ids = []
                    for i in range(2):
                        r = RoundModel(
                            table_id=tbl.id,
                            session_id=gs.id,
                            status="settled",
                            started_at=base + timedelta(minutes=i),
                        )
                        s.add(r)
                        await s.flush()
                        round_ids.append(r.id)

                        s.add(Participation(
                            round_id=r.id,
                            user_id=user_id,
                            seat_number=0,
                            bet_amount=25,
                            outcome="win" if i == 0 else "loss",
                            payout=50 if i == 0 else 0,
                        ))
                        s.add(LedgerEntry(
                            user_id=user_id,
                            round_id=r.id,
                            amount=25 if i == 0 else -25,
                            type="win" if i == 0 else "loss",
                            balance_after=10025 if i == 0 else 10000,
                            created_at=base + timedelta(minutes=i),
                        ))
        finally:
            await eng.dispose()

        # newest-first, matching the routes' ORDER BY ... DESC
        return {"table_id": str(tbl.id), "round_ids": [str(r) for r in reversed(round_ids)]}

    return _seed


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
            # There's no admin-promotion endpoint (by design), and users live in
            # Postgres now, so flip the column directly.
            eng = _throwaway_engine()
            try:
                sm = async_sessionmaker(bind=eng, expire_on_commit=False)
                async with sm() as s:
                    async with s.begin():
                        await s.execute(
                            update(User).where(User.id == user["id"]).values(is_admin=True)
                        )
            finally:
                await eng.dispose()

        login = await client.post(
            "/auth/login", data={"username": username, "password": password}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, user

    return _make
