# Blackjack Server

A multiplayer blackjack backend built to demonstrate real-time systems design, not to
demonstrate blackjack. The interesting parts are: an explicit finite-state machine for
game/hand progression, a single-writer-per-table concurrency model, WebSocket real-time
gameplay, and a ledger-derived (append-only) chip balance system modeled like a
financial system of record.

See [`docs/roadmap.md`](docs/roadmap.md) for the full learning roadmap, architecture
rationale, and phase-by-phase build plan this project follows.

## Status

Project scaffold only. See `docs/adr/` for the key design decisions and
`docs/roadmap.md` Part B for the phase plan (Phase 1: pure engine, in progress).

## Architecture, at a glance

- **`app/engine/`** — pure Python game rules (cards, deck, hand, state machine, dealer).
  Zero dependency on FastAPI/DB/Redis, so it's unit-testable in isolation and portable.
- **`app/tables/`** — single-writer-per-table actor: one asyncio task owns a table's
  live state and processes its event queue serially, sidestepping shared-state race
  conditions without explicit locks.
- **`app/api/`** — REST routes (auth, users, tables, history) and the WebSocket gateway
  for real-time gameplay.
- **`app/models/` + `app/db/`** — PostgreSQL system of record: users, tables, rounds,
  and an append-only ledger. Chip balances are derived from the ledger, never mutated
  in place.
- **`app/cache/`** — Redis for hot table-state snapshots, pub/sub fan-out across
  instances, sessions, and distributed locks.

## Running locally

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

Full stack (Postgres + Redis + app) via Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Testing

```bash
uv run pytest              # unit + integration
uv run mypy app
uv run ruff check .
```

## Docs

- `docs/adr/` — Architecture Decision Records for the key design choices (single-writer
  per table, Postgres-as-ledger, Redis pub/sub for scale-out, reconnect-via-snapshot).
