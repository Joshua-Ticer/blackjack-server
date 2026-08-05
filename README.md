# Blackjack Server

A multiplayer blackjack backend built to demonstrate real-time systems design — not to
demonstrate blackjack. The interesting parts: an explicit finite-state machine for
game/hand progression, a single-writer-per-table concurrency model, WebSocket real-time
gameplay, and a ledger-derived (append-only) chip balance system modeled like a
financial system of record.

**Try it in 30 seconds — no server, no database:**

```bash
uv sync
uv run python -m app.tui --demo
```

This launches the real [Textual](https://textual.textualize.io/) TUI client playing
against the real game engine (`app/engine/`) — full deal/hit/stand/split/settlement
logic, zero infrastructure required.

## Contents

- [What's built](#whats-built) — a map of every piece and where to look
- [Design decisions](#design-decisions) — the ADRs, if you want the "why"
- [Running the full stack](#running-the-full-stack) — server + Postgres + Redis
- [Tests](#tests) — what's covered and how to run it

## What's built

| Layer | Where | What it does |
|---|---|---|
| Game engine | [`app/engine/`](app/engine/) | Pure Python rules: cards, deck, hand, dealer, state machine, settlement. No FastAPI/DB/Redis dependency — unit-testable and portable in isolation. |
| Table concurrency | [`app/tables/`](app/tables/) | Single-writer-per-table actor: one asyncio task owns a table's live state and drains its event queue serially, avoiding shared-state races without explicit locks. See [ADR 0001](docs/adr/0001-single-writer-per-table.md). |
| REST API | [`app/api/routes/`](app/api/routes/) | Auth (signup/login), users, tables, round + ledger history — built on FastAPI. |
| WebSocket gateway | [`app/api/ws/gateway.py`](app/api/ws/gateway.py) | Real-time gameplay channel (`/ws/tables/{table_id}`), including reconnect-via-snapshot. See [ADR 0004](docs/adr/0004-reconnect-via-snapshot.md). |
| Persistence | [`app/models/`](app/models/), [`app/db/`](app/db/) | PostgreSQL system of record: users, tables, rounds, and an append-only ledger. Chip balances are derived from the ledger, never mutated in place. See [ADR 0002](docs/adr/0002-postgres-as-ledger.md). |
| Cache / pub-sub | [`app/cache/`](app/cache/) | Redis for hot table-state snapshots, cross-instance pub/sub fan-out, sessions, and distributed locks. See [ADR 0003](docs/adr/0003-redis-pubsub-for-scaleout.md). |
| TUI client | [`app/tui/`](app/tui/) | A full Textual terminal client — login, lobby, live table view, betting, hand actions — talking to the REST + WebSocket API. Includes an offline `--demo` mode driven directly by the engine. Built with [Claude Code](https://claude.com/claude-code): it's a thin client over the real backend, not the focus of this project, so it made more sense to generate than to hand-write. |

## Design decisions

Architecture Decision Records for the choices above, each with the tradeoff considered
and why the alternative was rejected:

- [0001 — Single-writer-per-table concurrency](docs/adr/0001-single-writer-per-table.md)
- [0002 — Postgres as the ledger](docs/adr/0002-postgres-as-ledger.md)
- [0003 — Redis pub/sub for scale-out](docs/adr/0003-redis-pubsub-for-scaleout.md)
- [0004 — Reconnect via snapshot, not event replay](docs/adr/0004-reconnect-via-snapshot.md)

The full phase-by-phase build plan and architecture rationale live in
[`docs/roadmap.md`](docs/roadmap.md).

## Running the full stack

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Requires a `.env` with `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `JWT_ALGORITHM`, and
`JWT_EXPIRE_MINUTES` — or just use Docker Compose below, which sets these for you.

Full stack (Postgres + Redis + app) via Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Then point the TUI at it:

```bash
uv run python -m app.tui --server http://localhost:8000
```

## Tests

```bash
uv run pytest              # integration, WebSocket, and TUI tests
uv run mypy app
uv run ruff check .
```

- [`tests/integration/`](tests/integration/) and [`tests/ws/`](tests/ws/) — REST and
  WebSocket behavior against a real Postgres + Redis.
- [`tests/tui/`](tests/tui/) — the Textual client driven end-to-end against a fake
  backend (login, lobby, live table, countdowns, snapshots).
- [`tests/load/`](tests/load/) — Locust load test for concurrent-table behavior.
- [`tests/unit/`](tests/unit/) — planned property-based/table-driven coverage for the
  engine (`app/engine/`); currently stubs, tracked in the roadmap.
