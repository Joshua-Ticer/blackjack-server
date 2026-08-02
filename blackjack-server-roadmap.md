# Multiplayer Blackjack Game Server — Learning Roadmap & Implementation Plan

A backend-engineering-first project plan. No frontend polish required — the goal is
demonstrable mastery of real-time systems, concurrency, state machines, and production
architecture.

---

## Part A — Cross-Cutting Foundations

Before phases, here's the conceptual map. Each phase will pull from this.

### 1. Backend Engineering Skills You'll Actually Learn

- **State machines** — modeling a process (a hand of blackjack, a table's lifecycle) as
  explicit states + transitions instead of scattered `if` flags.
- **Concurrency primitives** — locks, async tasks, race conditions, idempotency, and why
  "read-modify-write" is dangerous with shared state.
- **Real-time protocols** — WebSockets vs REST vs SSE, connection lifecycle, heartbeats,
  reconnect/resume semantics.
- **Data modeling** — normalizing game state into relational tables vs. keeping hot state
  in memory/Redis; the tradeoff between durability and speed.
- **API design** — REST resource modeling, request/response contracts, pagination,
  versioning, error semantics.
- **Auth & sessions** — token-based auth, session-to-connection binding (crucial for
  reconnects).
- **Caching & pub/sub** — Redis as both a cache and a message bus for horizontal scaling.
- **Testing discipline** — unit tests for pure logic, integration tests for API/WS,
  property-based tests for game rules, load tests for concurrency behavior.
- **Observability** — structured logging, metrics, tracing — how you'd actually debug this
  in production at 3am.
- **Containerization & CI/CD** — reproducible environments, automated test gates,
  deployment pipelines.
- **System design tradeoffs** — you'll be able to speak fluently about consistency vs.
  availability, single-writer patterns, sharding tables across server instances, etc.

### 2. Python Tools/Libraries (why each one, not just what)

| Tool | Role | Why it matters for this project |
|---|---|---|
| **FastAPI** | REST + WS framework | Async-native, Pydantic validation, dependency injection, auto OpenAPI docs |
| **Pydantic** | Data validation | Enforces contracts between client/server messages — critical when a malformed WS message could corrupt game state |
| **SQLModel or SQLAlchemy 2.0 (async)** | ORM | SQLModel = Pydantic + SQLAlchemy hybrid, good DX; plain SQLAlchemy = more control, more "real world" |
| **Alembic** | Migrations | You'll change your schema repeatedly; migrations are a core "adult engineering" skill |
| **PostgreSQL** | System of record | ACID guarantees for chip balances and game history — money-like data needs a real transactional DB |
| **Redis** | Hot state + pub/sub | In-memory table state, distributed locks, session store, and the message bus for scaling WS across processes |
| **pytest / pytest-asyncio** | Testing | Async test support is non-negotiable given your stack |
| **httpx** | Test client / async HTTP | FastAPI's recommended test client for async endpoints |
| **websockets / FastAPI's TestClient WS support** | WS testing | Simulate multiplayer clients in tests |
| **Docker / Docker Compose** | Local prod-like environment | Postgres + Redis + app as one reproducible stack |
| **GitHub Actions** | CI/CD | Lint, type-check, test, build image on every push |
| **Celery or RQ (optional)** | Background jobs | Async settlement, history archiving, scheduled table cleanup |
| **structlog or Python logging + JSON formatter** | Observability | Structured logs you can actually query |
| **Prometheus client + Grafana (optional)** | Metrics | Time-in-state, connection counts, bet volume — great for a "resume screenshot" |
| **OpenTelemetry (optional)** | Tracing | Follow a single bet through REST → WS → DB → Redis |
| **mypy** | Static typing | Type-driven design reduces a whole class of bugs in state machines |
| **locust or custom asyncio load script** | Load testing | Simulate hundreds of concurrent players/tables |

### 3. Full System Architecture (high level)

```
                        ┌─────────────────────┐
                        │       Client(s)      │
                        │ (CLI / simple web UI)│
                        └──────────┬───────────┘
                     REST (auth,   │   WebSocket (gameplay)
                     lobby, history)│
                                   ▼
                     ┌─────────────────────────────┐
                     │        FastAPI App           │
                     │  ┌───────────┐ ┌────────────┐│
                     │  │ REST      │ │ WS Gateway  ││
                     │  │ Routers   │ │ (per table) ││
                     │  └─────┬─────┘ └──────┬─────┘│
                     │        │              │       │
                     │  ┌─────▼──────────────▼─────┐ │
                     │  │   Game Engine (pure Py)   │ │
                     │  │  Table Manager / State     │ │
                     │  │  Machine per table         │ │
                     │  └─────┬──────────────┬──────┘ │
                     └────────┼──────────────┼────────┘
                              │              │
                  ┌───────────▼───┐   ┌──────▼─────────┐
                  │   PostgreSQL   │   │      Redis      │
                  │ (users, chips, │   │ (live table     │
                  │  hand history, │   │  state, pub/sub,│
                  │  audit log)    │   │  sessions, locks)│
                  └────────────────┘   └──────────────────┘
                              │
                     ┌────────▼────────┐
                     │ Celery/RQ worker │ (optional: settlement,
                     │  + broker(Redis) │  archiving, cleanup jobs)
                     └──────────────────┘
```

**Key architectural decision to be able to defend in interviews:** where does
*authoritative* game state live while a hand is in progress? The recommended answer for
this project: **in-memory per-table state (owned by one asyncio task per table) backed by
Redis for crash recovery/horizontal scaling, with PostgreSQL as the durable ledger once a
hand/round completes.** This "single-writer per table" pattern sidesteps most race
conditions and is a very interview-friendly design to explain.

### 4. Database Models (Postgres, durable/system-of-record data)

Rough entity list — you'll refine this in Phase 4:

- **User** — id, username, hashed_password, email, chip_balance, created_at
- **Table** — id, name, min_bet, max_bet, max_seats, status (open/closed), created_at
- **GameSession** (a.k.a. "Shoe" or "Round batch") — id, table_id, started_at, ended_at,
  deck_seed/shuffle metadata
- **Round** — id, table_id, session_id, dealer_hand (json), status, started_at, ended_at
- **Seat/Participation** — id, round_id, user_id, seat_number, bet_amount, hand(s) (json,
  supports splits), outcome (win/lose/push/blackjack/bust), payout
- **Transaction/LedgerEntry** — id, user_id, round_id (nullable), amount, type
  (bet/payout/buy-in/adjustment), balance_after, created_at — this is your **audit trail**;
  treat chip balance like real money internally even though it's virtual (great interview
  talking point: "I modeled it like a financial ledger, append-only, balance derived from
  sum of entries").
- **Session/Connection** (could live in Redis instead) — user_id, table_id, connection
  status, last_seen — supports reconnect logic.

Design principle to state explicitly in your README: **balances are never mutated
in-place by game logic alone — every chip movement is a LedgerEntry, and `chip_balance`
is either a cached column reconciled from the ledger or fully derived.** This is exactly
how real-money systems are built and is a strong signal to reviewers.

### 5. WebSocket / Event Flow

Design your protocol like a tiny RPC system with typed envelopes (Pydantic models both
directions):

**Client → Server events**
- `join_table` — attach connection to a table channel
- `sit` — take a seat with a buy-in amount
- `place_bet`
- `action` — `hit` / `stand` / `double` / `split` / `surrender`
- `leave_table`
- `ping` (heartbeat)

**Server → Client events**
- `table_state` — full snapshot on join (for late-joiners/reconnects)
- `state_delta` — incremental update (new card dealt, player acted, etc.)
- `round_started`, `betting_open`, `betting_closed`
- `player_turn` — whose turn, with a timeout
- `round_result` — payouts, outcomes
- `error` — invalid action, insufficient chips, etc.
- `pong`

**Flow for one round (sequence):**
1. Table manager transitions table state → `BETTING_OPEN`, broadcasts to all connected
   clients at that table.
2. Each seated player sends `place_bet`; server validates against ledger, locks the bet,
   broadcasts `state_delta`.
3. Timer expires or all bets in → state → `DEALING`. Dealer deals via the pure game
   engine; broadcast each card as a `state_delta` (nice UX + testable increments).
4. State → `PLAYER_TURN(seat=1)`; server sends `player_turn` with an action deadline.
   Player acts → engine validates/applies → broadcast delta → advance to next seat or
   dealer.
5. State → `DEALER_TURN` → engine plays fixed dealer strategy → broadcast.
6. State → `SETTLEMENT` → engine computes outcomes → ledger entries written to Postgres →
   broadcast `round_result` → state → `BETTING_OPEN` again (or `IDLE` if no players).

**Reconnect handling:** on WS reconnect, client sends `join_table` (or resumes via a
session token); server responds with a full `table_state` snapshot rebuilt from
in-memory/Redis state rather than replaying every delta — much simpler and more robust.

### 6. Blackjack Game State Machine

This is the heart of the "backend engineer" story — build it in pure Python, with zero
I/O, fully unit-testable.

**Table-level states:**
```
IDLE → BETTING_OPEN → BETTING_CLOSED → DEALING → PLAYER_TURNS → DEALER_TURN
  → SETTLEMENT → IDLE (loop)
```

**Per-hand states (nested inside PLAYER_TURNS, matters for splits):**
```
ACTIVE → (HIT loop) → STANDING | BUSTED | BLACKJACK | DOUBLED | SURRENDERED
```

Model it with an explicit `enum.Enum` for states and a transition table/dict mapping
`(state, event) -> new_state`, rather than nested if/else. This lets you write a single
`can_transition(state, event) -> bool` and unit-test every legal/illegal transition —
a very "I understand FSMs" artifact for your repo.

Things the engine must own (and be tested against), independent of any networking:
- Shoe/deck construction, shuffling (seeded, for reproducible tests), penetration/cut card
- Deal order, hole card handling
- Hit/stand/double/split/surrender legality rules (including split-aces restrictions,
  double-after-split policy — pick and document a rule set)
- Bust detection, soft/hard totals (Ace as 1 or 11)
- Dealer fixed strategy (hit until 17, stand on soft 17 — document your choice)
- Blackjack payout (3:2 or 6:5 — document your choice)
- Push/win/loss/blackjack settlement math

### 7. Concurrency & Race Conditions

This is where you'll separate yourself from most portfolio projects. Concrete hazards and
your mitigations:

- **Two players acting "simultaneously" on the same table** → mitigate with a
  **single-writer-per-table** model: one asyncio task (or actor) owns a table's mutable
  state; all events for that table go through an `asyncio.Queue` processed sequentially.
  No shared-memory locking needed within a process because there's no concurrent mutation
  — just serialized processing.
- **Multiple server processes/instances** (needed for horizontal scale) → the naive
  in-process queue doesn't work across processes. Use **Redis-based distributed locks**
  (`SET NX PX` pattern, or `redlock`) around a table's critical section, or better: pin
  each table to exactly one worker via consistent hashing / a leader-election scheme, and
  use Redis pub/sub to fan out state to all connected clients regardless of which process
  holds their WS.
- **Double-spend on bets** — a malicious/buggy client sends `place_bet` twice rapidly →
  idempotency: require an `action_id` (UUID) per client action; server deduplicates
  within a round.
- **Balance race** — two concurrent bets both read balance=100, both allow a 100-chip
  bet → because the table is single-writer, this collapses to a non-issue at the table
  level, but ledger writes to Postgres should also use a `SELECT ... FOR UPDATE` or an
  atomic `UPDATE ... WHERE balance >= amount RETURNING` to be safe if balance is ever
  touched from multiple code paths (e.g., an admin adjustment endpoint running
  concurrently with gameplay).
- **Reconnect race** — player disconnects mid-turn, action timer fires "auto-stand,"
  then a stale WS message from the old connection arrives → tag every table snapshot
  with a monotonic `state_version`; reject/ignore actions referencing a stale version.
- **Crash recovery** — process dies mid-round with an in-memory-only table → periodically
  (or on every state transition) persist a compact snapshot to Redis so a restarted
  worker can resume instead of losing the round.

Being able to whiteboard this section is genuinely FAANG-interview-relevant material
(it's basically a mini "design a multiplayer game backend" system design question).

### 8. Project Folder Structure

```
blackjack-server/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── config.py                # settings via pydantic-settings
│   ├── api/
│   │   ├── deps.py              # shared dependencies (auth, db session)
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── tables.py
│   │   │   └── history.py
│   │   └── ws/
│   │       ├── gateway.py       # WS endpoint, connection lifecycle
│   │       └── schemas.py       # Pydantic event envelopes
│   ├── engine/                  # PURE PYTHON, no FastAPI/DB imports
│   │   ├── card.py
│   │   ├── deck.py
│   │   ├── hand.py
│   │   ├── rules.py
│   │   ├── state_machine.py
│   │   └── dealer.py
│   ├── tables/
│   │   ├── table_manager.py     # owns per-table asyncio task/queue
│   │   └── table_actor.py
│   ├── models/                  # SQLAlchemy/SQLModel ORM models
│   │   ├── user.py
│   │   ├── table.py
│   │   ├── round.py
│   │   └── ledger.py
│   ├── db/
│   │   ├── session.py
│   │   └── base.py
│   ├── cache/
│   │   └── redis_client.py
│   ├── services/                # orchestration: engine + db + redis glue
│   │   ├── betting_service.py
│   │   ├── settlement_service.py
│   │   └── reconnect_service.py
│   └── workers/                 # celery/rq tasks (optional)
├── tests/
│   ├── unit/                    # pure engine tests, no I/O
│   ├── integration/             # API + DB tests
│   ├── ws/                      # WebSocket flow tests
│   └── load/                    # locust/asyncio load scripts
├── alembic/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/workflows/ci.yml
├── pyproject.toml
└── README.md
```

The **`engine/` having zero dependency on FastAPI/DB/Redis** is itself a design decision
worth calling out in your README — it's what makes Phase 1 pure-unit-testable and keeps
your core logic portable/reusable.

### 9. Testing Strategy

- **Unit tests (engine)**: deterministic via seeded shuffles; table-driven tests for every
  state transition; edge cases (splitting aces, blackjack vs. 21-after-split, dealer
  soft-17, bust ordering, surrender timing).
- **Property-based tests** (via `hypothesis`): e.g., "for any sequence of legal actions,
  total chips in the system before and after settlement is conserved" — a great invariant
  to test and mention in interviews.
- **Integration tests (REST)**: `httpx.AsyncClient` against a test Postgres (via
  `docker-compose` test profile or `pytest-postgresql`); test auth, buy-in, history
  endpoints.
- **WebSocket flow tests**: spin up the app with `TestClient`/`websockets` library,
  simulate 2–4 concurrent "players" scripted through a full round, assert broadcast
  ordering and final ledger state.
- **Concurrency/race tests**: deliberately fire simultaneous actions (e.g., two `hit`
  requests from the same seat) and assert only one is honored — this is the test that
  proves your concurrency design works, not just that it "looks" thread-safe.
- **Load tests**: simulate N tables × M players with `locust` or a raw `asyncio` script
  hammering the WS gateway; measure p99 action latency and connection scaling; this feeds
  directly into an observability phase.
- **CI gate**: unit + integration on every PR; load tests as a separate manual/scheduled
  workflow.

### 10. Making This Impressive for Big Tech SWE Recruiting

- **Lead with the systems story, not the game.** Your README's first paragraph should be
  about the real-time state machine, concurrency model, and ledger design — "blackjack"
  is just the vehicle.
- **Write an ADR (Architecture Decision Record) doc** for 3–4 key decisions: single-writer
  per table, Postgres-as-ledger, Redis pub/sub for scale-out, reconnect-via-snapshot. This
  is exactly what senior engineers write and reviewers notice it.
- **Include a "Concurrency & Correctness" section** with the race conditions you
  identified and how you tested for them — this answers the interview question before
  it's asked.
- **Diagram everything** — sequence diagrams for a round, the state machine diagram, the
  deployment diagram. Recruiters and interviewers skim; diagrams get read.
- **Add metrics/dashboards (Phase 7)** — a Grafana screenshot of live tables/connections
  in your README is a strong, uncommon signal.
- **Load test numbers in the README** — "sustained N concurrent WS connections across M
  tables at p99 action latency of X ms" is a concrete, defensible claim.
- **Real CI/CD, not just a badge** — lint + type-check + test + build on every push;
  mention branch protection.
- **Document the rules you chose** (payout ratio, soft-17, DAS policy) — shows attention
  to spec-writing and edge-case thinking.
- **Write a short "what I'd do differently at 10x scale" section** — sharding strategy,
  moving to a dedicated actor framework, event sourcing instead of snapshotting. This
  signals growth trajectory, which is exactly what internship reviewers are trying to
  gauge.

---

## Part B — Phase-by-Phase Plan

### Phase 1: Core Blackjack Engine (pure Python)

**Build:** `engine/` package — `Card`, `Deck` (seeded shuffle), `Hand` (value calc incl.
soft aces), `Rules` (legal actions given a hand/table rules), `StateMachine` (enum states
+ transition table), `Dealer` (fixed strategy), a `Round` orchestrator that ties them
together with no I/O at all — pure functions/classes, deterministic given a seed.

**Concepts to understand:** finite state machines, enums as first-class control flow,
immutability vs. mutation tradeoffs for hand/table state, deterministic randomness for
testing, separation of "policy" (rules) from "mechanism" (dealing).

**Files/modules:** `card.py`, `deck.py`, `hand.py`, `rules.py`, `state_machine.py`,
`dealer.py`, `round.py`.

**Common beginner mistakes:**
- Hardcoding ace value as 11 and special-casing everywhere instead of computing
  soft/hard totals generically.
- Letting the state machine be implicit (a pile of booleans like `is_dealing`,
  `is_player_turn`) instead of one explicit state field with an enum.
- Mixing display/formatting logic into the engine.
- Not seeding the shuffle, making tests flaky/non-reproducible.
- Forgetting split-hand edge cases (re-splitting, split aces get one card only, etc.) —
  decide your rule set up front and write it down.

**What "done" looks like:** you can run a fully scripted multi-player round entirely in a
Python REPL/script with no server, no DB, no network — deterministic output given a seed,
100% unit-test coverage on the engine, and a written rules document.

**Resume bullet potential:** *"Designed a pure-Python blackjack rules engine with an
explicit finite-state machine (12+ states/transitions) covering splits, doubles, and
soft-ace logic, achieving 100% branch coverage via seeded deterministic unit tests."*

---

### Phase 2: REST API for Users, Tables, and Game History

**Build:** FastAPI app skeleton; auth (signup/login, hashed passwords, JWT or session
token); `Table` CRUD (list/create tables — admin-only creation is fine); `GET
/history` endpoints backed by (for now) an in-memory or SQLite store, to be swapped for
Postgres in Phase 4 — or just do Postgres now if you'd rather not throw work away (your
call).

**Concepts:** REST resource design, request/response schemas via Pydantic, dependency
injection for auth/db sessions, password hashing (bcrypt/argon2), JWT structure and
expiry, pagination for history endpoints, proper HTTP status codes/error models.

**Files/modules:** `api/routes/auth.py`, `api/routes/users.py`, `api/routes/tables.py`,
`api/routes/history.py`, `api/deps.py`, `config.py`.

**Common beginner mistakes:**
- Storing plaintext passwords or rolling your own crypto.
- Putting business logic directly in route handlers instead of a `services/` layer
  (makes testing and later WS reuse painful).
- No pagination on history endpoints — will bite you immediately once you have real data.
- Inconsistent error response shapes across endpoints.

**What "done" looks like:** a Postman/HTTPie-testable API with signup, login, list
tables, and (stubbed) history, all covered by `httpx`-based integration tests, and OpenAPI
docs auto-generated and readable at `/docs`.

**Resume bullet potential:** *"Built a FastAPI REST service with JWT auth, dependency-
injected DB sessions, and a service-layer architecture separating business logic from
HTTP concerns."*

---

### Phase 3: WebSocket Real-Time Gameplay

**Build:** the WS gateway (`api/ws/gateway.py`) that accepts connections, authenticates
them, and routes events; the `TableManager`/`TableActor` that owns one table's live state
and processes its event queue serially; wiring the Phase 1 engine into this actor so
real players can play a real round over WebSockets end-to-end (state still in-memory
only — Postgres comes next phase).

**Concepts:** WebSocket connection lifecycle (accept/receive/send/close), the
single-writer-per-table actor pattern via `asyncio.Queue` + one dedicated task per table,
broadcast fan-out to N connections, structured event envelopes (Pydantic unions or a
`type` discriminator field), heartbeats/timeouts for idle/dead connections.

**Files/modules:** `api/ws/gateway.py`, `api/ws/schemas.py`, `tables/table_manager.py`,
`tables/table_actor.py`.

**Common beginner mistakes:**
- Mutating table state directly from the WS handler for each connection (reintroduces
  race conditions) instead of funneling everything through the actor's queue.
- No message schema/validation — trusting raw client JSON.
- Forgetting to remove dead connections from the broadcast list, causing errors/leaks.
- No action deadline/timeout handling, so one AFK player freezes the whole table.
- Broadcasting the *entire* internal object graph (leaking other players' hole cards,
  internal deck state) instead of a sanitized view model.

**What "done" looks like:** you can open 2–4 WS client scripts (or a `websockets`-based
test harness), sit them at a table, bet, and play a full round with correct real-time
broadcasts and no shared-state bugs under rapid concurrent actions.

**Resume bullet potential:** *"Implemented a real-time multiplayer game gateway using
FastAPI WebSockets with a single-writer actor-per-table concurrency model, eliminating
shared-state race conditions without explicit locking."*

---

### Phase 4: Persistence with PostgreSQL

**Build:** SQLAlchemy/SQLModel models for `User`, `Table`, `GameSession`, `Round`,
`Seat/Participation`, `LedgerEntry`; Alembic migrations; wire the settlement step of a
round to write ledger entries + round history transactionally; swap Phase 2's stubs for
real Postgres-backed queries.

**Concepts:** relational modeling, foreign keys/constraints, transactions (`COMMIT`/
`ROLLBACK`), the ledger/append-only balance pattern, migrations as versioned schema
change, `async` SQLAlchemy sessions, N+1 query avoidance.

**Files/modules:** `models/*.py`, `db/session.py`, `db/base.py`, `alembic/versions/*`,
`services/settlement_service.py`.

**Common beginner mistakes:**
- Mutating `user.chip_balance` directly from multiple places instead of deriving it from
  the ledger (or at least wrapping every mutation in one audited function).
- Not wrapping settlement (multiple ledger writes + round status update) in a single DB
  transaction — partial failure corrupts state.
- Forgetting indexes on frequently-queried columns (user_id, table_id, created_at).
- Writing migrations by hand instead of `alembic revision --autogenerate` + review.

**What "done" looks like:** a full round played over WS results in durable, queryable
Postgres rows; killing and restarting the server doesn't lose completed-round history;
`GET /history` returns real data with correct pagination.

**Resume bullet potential:** *"Designed an append-only ledger schema for virtual-currency
settlement, guaranteeing auditability and atomicity via transactional writes across round
and balance updates."*

---

### Phase 5: Redis for Table State, Sessions, Pub/Sub, Caching

**Build:** move live table state (or a periodic snapshot of it) into Redis so a crashed/
restarted server can recover; use Redis pub/sub so multiple app instances can broadcast to
WS connections they don't directly own; store session/auth tokens in Redis with TTL;
cache read-heavy endpoints (e.g., table list) with sensible invalidation.

**Concepts:** Redis data structures (strings/hashes/JSON for snapshots, pub/sub channels),
horizontal scaling of stateful WS servers, distributed locks (`SET NX PX`), cache
invalidation strategy, session vs. connection (a user can reconnect from a new WS
connection but same session).

**Files/modules:** `cache/redis_client.py`, `services/reconnect_service.py`,
`tables/table_actor.py` (extended to snapshot/restore).

**Common beginner mistakes:**
- Treating Redis as a second source of truth instead of a cache/hot-path store — Postgres
  should remain authoritative for anything durable.
- No TTL on session keys, causing unbounded growth.
- Race between a Redis snapshot write and the in-memory state changing again immediately
  after — snapshot on every state transition, not on a timer, or accept some staleness
  and document it.
- Not handling Redis connection loss gracefully (should degrade, not crash the app).

**What "done" looks like:** you can kill the server mid-round, restart it, and a
reconnecting client resumes the round from a Redis-restored snapshot; you can run two app
instances behind a simple round-robin and prove cross-instance broadcast works via
pub/sub.

**Resume bullet potential:** *"Added Redis-backed state snapshotting and pub/sub fan-out,
enabling horizontal scaling of the WebSocket gateway and sub-second crash recovery for
in-progress games."*

---

### Phase 6: Testing, Load Simulation, and Reliability

**Build:** fill out the full test pyramid described in Part A §9; write a load-testing
script (locust or asyncio) simulating dozens of tables and hundreds of players; add
chaos-style tests (kill a connection mid-action, send malformed events, double-send
actions) and assert the system degrades safely.

**Concepts:** test pyramids, property-based testing, load testing methodology (ramp-up,
steady state, p50/p95/p99 latency), chaos/fault injection, flaky-test hygiene (seeded
randomness, no real sleeps where avoidable).

**Files/modules:** `tests/unit/`, `tests/integration/`, `tests/ws/`, `tests/load/
locustfile.py`.

**Common beginner mistakes:**
- Only testing the happy path; never testing simultaneous/duplicate/out-of-order actions.
- Using real `time.sleep`/wall-clock timing in tests instead of injectable clocks/mocked
  timeouts, causing slow/flaky CI.
- Load testing against your laptop's dev server instead of the Dockerized "prod-like"
  stack, giving misleading numbers.
- Not asserting on *system invariants* (e.g., total chips conserved) in addition to
  individual endpoint responses.

**What "done" looks like:** CI runs unit+integration on every PR in under a few minutes;
you have a documented load-test run with concrete latency/throughput numbers; you have at
least a few "adversarial" tests proving your concurrency design holds under stress.

**Resume bullet potential:** *"Load-tested the WebSocket gateway to N concurrent
connections across M tables using Locust, identifying and fixing a [specific bottleneck],
improving p99 action latency from X ms to Y ms."* (fill in real numbers once measured —
this kind of before/after is gold for interviews.)

---

### Phase 7: Docker, CI/CD, Observability, and Deployment Polish

**Build:** multi-stage `Dockerfile`; `docker-compose.yml` wiring app + Postgres + Redis
(+ worker if using Celery/RQ) for one-command local prod-like startup; GitHub Actions
workflow (lint → type-check → test → build image); structured JSON logging; Prometheus
metrics endpoint (connection count, active tables, action latency histogram); optional
Grafana dashboard; optional OpenTelemetry tracing across a request's REST → WS → DB →
Redis path; a deployment write-up (even if you don't actually host it long-term — e.g.,
"deployed to Fly.io/Render for demo purposes").

**Concepts:** multi-stage Docker builds, container networking, environment-based config
(12-factor app), CI pipelines as code, the RED/USE metrics frameworks, log aggregation
basics, tracing/span concepts.

**Files/modules:** `docker/Dockerfile`, `docker/docker-compose.yml`,
`.github/workflows/ci.yml`, `app/observability/metrics.py`, `app/observability/
logging.py`.

**Common beginner mistakes:**
- One giant Dockerfile layer that rebuilds everything on every code change instead of
  layering dependency install separately from app code copy.
- Secrets committed to `docker-compose.yml` instead of `.env` + `.gitignore`.
- CI that only runs `pytest` with no lint/type-check gate.
- Metrics added but never actually looked at / no dashboard — do at least one screenshot.

**What "done" looks like:** `docker compose up` gives a fully working local stack from a
clean clone; a green CI badge on your README; a metrics endpoint you can `curl` and (ideally)
a Grafana screenshot in your README; a short "Running Locally" and "Architecture" section
in the README that a stranger could follow in under 10 minutes.

**Resume bullet potential:** *"Containerized a multi-service backend (FastAPI, Postgres,
Redis) with Docker Compose and GitHub Actions CI/CD, and instrumented Prometheus metrics
for connection health, table throughput, and action latency."*

---

## Part C — Final Architecture Diagram (detailed text form)

```
                                   Internet
                                      │
                         ┌────────────┴────────────┐
                         │   Load Balancer (opt.)    │
                         └────────────┬────────────┘
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
             ┌──────▼──────┐   ┌──────▼──────┐   ┌───────▼─────┐
             │ FastAPI      │   │ FastAPI      │   │ FastAPI      │
             │ Instance A   │   │ Instance B   │   │ Instance C   │
             │ (REST + WS)  │   │ (REST + WS)  │   │ (REST + WS)  │
             └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
                    │                  │                  │
                    │   Redis Pub/Sub  │  (cross-instance  │
                    │   broadcast for  │   WS fan-out)     │
                    └────────┬─────────┴─────────┬─────────┘
                             │                   │
                     ┌───────▼───────┐   ┌───────▼────────┐
                     │     Redis      │   │  PostgreSQL     │
                     │ - table state  │   │ - users         │
                     │   snapshots    │   │ - tables        │
                     │ - sessions     │   │ - rounds        │
                     │ - locks        │   │ - ledger entries│
                     │ - pub/sub bus  │   │ - audit history │
                     └────────────────┘   └─────────────────┘
                             │
                     ┌───────▼────────┐
                     │ Celery/RQ Worker│ (optional)
                     │ - settlement    │
                     │ - archiving     │
                     │ - cleanup jobs  │
                     └─────────────────┘

     Observability sidecar (all instances export to):
     ┌────────────┐   ┌────────────┐   ┌───────────────┐
     │ Prometheus │──▶│  Grafana   │   │ OpenTelemetry  │
     │  (metrics) │   │(dashboards)│   │ Collector      │
     └────────────┘   └────────────┘   └───────────────┘
```

Note: each table is "owned" by exactly one instance's actor at a time (via a lock/lease
in Redis); other instances relay client actions for that table over Redis pub/sub to the
owning instance and relay broadcasts back out to their own locally-connected clients.
This is the key idea to be able to explain fluently.

---

## Part D — Interview Concepts Checklist

After building this, you should be able to explain, from first principles, without
notes:

**State machines & game logic**
- Why you modeled the game as an explicit FSM instead of boolean flags
- How split hands nest inside the table-level state machine
- How you made shuffling deterministic for tests while still "random" in production

**Concurrency**
- What race conditions exist in a naive multiplayer game server
- Why single-writer-per-table + a queue avoids locks within a process
- How you'd extend this to multiple processes (distributed locks, leader/owner per table,
  pub/sub relay)
- The double-spend/idempotency problem and how `action_id` deduplication solves it
- Optimistic vs. pessimistic concurrency control, and which you used where

**Real-time systems**
- WebSocket connection lifecycle and failure modes
- Why you snapshot-and-resume on reconnect instead of replaying an event log (and the
  tradeoff: simpler, but not full history — vs. event sourcing, which is more complex but
  gives replayability)
- How you'd add horizontal scaling to a stateful WS service (this is a classic system
  design interview question — you'll have *actually built* a version of the answer)

**Data & persistence**
- Why chip balances are ledger-derived rather than mutated in place
- ACID transactions and why settlement must be atomic
- The tradeoff between Postgres (durable, transactional) and Redis (fast, ephemeral) and
  why each holds what it holds
- Migration strategy and why schema changes are versioned

**Testing & reliability**
- The test pyramid you built and why unit tests target the pure engine specifically
- What a property-based "chip conservation" test actually proves
- How you load-tested and what bottleneck you found and fixed (have real numbers ready)

**Systems/production**
- 12-factor config, container layering, CI gates
- What metrics you'd watch in production and why (connection count, action latency,
  error rate, table occupancy)
- What you'd change to support 10x the load (sharding tables by hash across more
  instances, moving from snapshot-restore to full event sourcing, read replicas for
  history queries, etc.)

---

## Suggested Order of Attack

1. Phase 1 fully done and tested before touching FastAPI at all — resist the urge to
   wire up a server early; a rock-solid pure engine makes every later phase easier.
2. Phases 2 and 3 can interleave slightly (basic auth needed before WS auth), but keep
   REST and WS concerns in separate modules from day one.
3. Phase 4 before Phase 5 — get a correct single-instance, durable system working before
   you introduce the added complexity of distributed state.
4. Phase 6 should be continuous, not a one-time phase at the end — but doing a dedicated
   hardening pass here is still valuable for the "load test numbers in the README" payoff.
5. Phase 7 last, but budget real time for it — this is often the difference between a
   good project and one that visibly looks like it was built by someone who's shipped
   software before.

Good luck — this is a strong project. The single highest-leverage thing you can do for
recruiting impact is writing the README and ADRs as if you're explaining the system to a
new hire on your team, not describing "a blackjack game."
