"""Run before locust: creates an admin user (no admin-promotion endpoint exists by
design), enough tables to seat every planned virtual user, and a pool of
pre-hashed player accounts for locust to log into.

    uv run python tests/load/seed.py --tables 20 --players 150

Needs at least ceil(peak_users / max_seats) tables so users don't queue up on a
full table, and at least as many player accounts as concurrent users -- signup
runs Argon2 (deliberately expensive, ~2s of CPU per call), so doing it for 100
players at locust spawn time measures Argon2's cost, not the WS gateway's.
Pre-hashing here, once, off the clock, keeps the load test measuring what it's
meant to measure. Points at whatever DATABASE_URL the environment resolves to
-- run against the Dockerized stack (`docker compose -f docker/docker-compose.yml
up -d`), not a laptop dev server, or the numbers this collects are meaningless.

Every run gets a fresh batch of tables (written to tables.json alongside this
file) rather than reusing whatever "Load Test Table *" rows already exist.
Seats are sticky by design (a disconnected player keeps their seat so they can
reconnect -- see ADR 0004), and locust doesn't reliably run a user's cleanup
hook when a headless run just hits --run-time and kills everything, so reusing
old tables across runs means starting from however full a previous run left
them, not from empty. Player accounts don't have this problem (logging in
doesn't seat you anywhere), so those *are* safely reused between runs.
"""

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from passlib.context import CryptContext
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.table import Table
from app.models.user import User

ADMIN_USERNAME = "loadtest_admin"
ADMIN_PASSWORD = "loadtest-admin-pw"
TABLE_NAME_PREFIX = "Load Test Table"
PLAYER_USERNAME_PREFIX = "loadtest_player_"
PLAYER_PASSWORD = "loadtest-player-pw"
MANIFEST_PATH = Path(__file__).parent / "tables.json"
PLAYERS_MANIFEST_PATH = Path(__file__).parent / "players.json"

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


async def ensure_admin() -> None:
    async with SessionLocal() as session:
        async with session.begin():
            existing = await session.scalar(
                select(User).where(User.username == ADMIN_USERNAME)
            )
            if existing is None:
                session.add(
                    User(
                        username=ADMIN_USERNAME,
                        hashed_password=pwd_context.hash(ADMIN_PASSWORD),
                        is_admin=True,
                    )
                )


async def create_fresh_tables(count: int) -> list[str]:
    run_tag = uuid.uuid4().hex[:8]
    tables = [
        Table(
            name=f"{TABLE_NAME_PREFIX} {run_tag} {i}",
            min_bet=5,
            max_bet=500,
            max_seats=6,
        )
        for i in range(count)
    ]
    async with SessionLocal() as session:
        async with session.begin():
            session.add_all(tables)
            await session.flush()
            ids = [str(t.id) for t in tables]

    MANIFEST_PATH.write_text(json.dumps(ids))
    return ids


async def ensure_players(count: int) -> None:
    hashed = pwd_context.hash(PLAYER_PASSWORD)
    async with SessionLocal() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    select(User.username).where(
                        User.username.like(f"{PLAYER_USERNAME_PREFIX}%")
                    )
                )
            ).scalars().all()
            existing = set(rows)
            for i in range(count):
                username = f"{PLAYER_USERNAME_PREFIX}{i:04d}"
                if username not in existing:
                    session.add(User(username=username, hashed_password=hashed))
    PLAYERS_MANIFEST_PATH.write_text(json.dumps(count))


async def main(tables: int, players: int) -> None:
    await ensure_admin()
    ids = await create_fresh_tables(tables)
    await ensure_players(players)
    print(f"admin ready: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print(f"tables ready: {len(ids)} fresh tables written to {MANIFEST_PATH}")
    print(
        f"players ready: {players} accounts '{PLAYER_USERNAME_PREFIX}0000'.."
        f"'{PLAYER_USERNAME_PREFIX}{players - 1:04d}', password '{PLAYER_PASSWORD}'"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tables", type=int, default=20)
    parser.add_argument("--players", type=int, default=150)
    args = parser.parse_args()
    asyncio.run(main(args.tables, args.players))
