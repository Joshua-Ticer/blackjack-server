# Phase 2: REST API for Users, Tables, and Game History

## Summary

Phase 2 builds the FastAPI REST API: signup/login with JWT auth, a current-user
profile endpoint, table listing/admin-only creation, and a dummy paginated (stubbed) round/ledger
history. Persistence for this phase is **in-memory** — no database yet.
Postgres-backed persistence replaces the stubs in Phase 4.

## What "done" means here

- Signup, login, list tables, and (stubbed) history are all reachable and covered by
  `httpx.AsyncClient`-based integration tests.
- OpenAPI docs are auto-generated and readable at `/docs`.
- Passwords are never stored in plaintext; sessions are JWT bearer tokens.

## File-by-file

### `app/config.py`
`Settings` (pydantic-settings), loaded from environment / `.env`. Holds `secret_key`,
`jwt_algorithm`, `jwt_expire_minutes` — everything auth needs to sign and verify tokens.
A single module-level `settings` instance is imported everywhere else that needs config.

### `app/api/deps.py`
Shared FastAPI dependencies, plus the Phase 2 stand-in "database":

- `User` (Pydantic model) — `id`, `username`, `hashed_password`, `chip_balance` (defaults
  to 10000), `is_admin`.
- `_users_by_id` / `_users_by_username` — plain dicts acting as the in-memory user store.
  Deliberately module-level so they're a drop-in seam for Phase 4.
- `create_user(username, hashed_password)` — inserts into both dicts, returns the `User`.
- `get_user_by_username(username)` — lookup used by both signup (duplicate check) and
  login.
- `oauth2_scheme` — `OAuth2PasswordBearer(tokenUrl="/auth/login")`, wired into FastAPI's
  dependency injection so protected routes just declare `Depends(get_current_user)`.
- `get_current_user(token)` — decodes the JWT with `settings.secret_key`, pulls the
  user id out of the `sub` claim, and loads the `User`. Raises `401` on any decode
  failure, missing/malformed `sub`, or unknown user id.

### `app/api/routes/auth.py`
`POST /auth/signup` and `POST /auth/login`.

- Password hashing uses `passlib`'s `CryptContext` configured for **argon2**.
- `signup`: rejects duplicate usernames (`400`), hashes the password, delegates to
  `deps.create_user`, and returns `UserPublic` (never the hash).
- `login`: accepts an `OAuth2PasswordRequestForm` (standard `username`/`password` form
  body, not JSON — this is what makes it compatible with the OpenAPI "Authorize" button
  in `/docs` and with `oauth2_scheme`). Verifies the password with
  `pwd_context.verify`, then signs a JWT: `sub` = user id, `exp` = now +
  `jwt_expire_minutes`, algorithm from `settings.jwt_algorithm`. Wrong password or
  unknown username both return a generic `401`.
- `UserPublic` / `TokenResponse` are the response schemas — `UserPublic` is also reused
  by `users.py` so `/users/me` and `/auth/signup` return an identically-shaped user.

### `app/api/routes/users.py`
`GET /users/me` — the only route so far. Protected by
`Depends(get_current_user)`; returns the caller's own profile (including
`chip_balance`). Nothing here queries by arbitrary user id — you can only ever fetch
yourself, since the user comes from the verified JWT, not a path/query param.

### `app/api/routes/tables.py`
In-memory `Table` CRUD:

- `GET /tables` — list all tables, no auth required (table listings are public, like a
  lobby).
- `POST /tables` — **admin-only** (checks `user.is_admin`, `403` otherwise). Generates a
  `uuid4` id and appends to the module-level `_tables` list.
- `GET /tables/{table_id}` — linear scan of `_tables`; `404` if not found. Fine at this
  scale/phase; Phase 4 replaces this with an indexed Postgres lookup.

There's currently no route that promotes a user to admin — `is_admin` can only be set by
directly mutating the in-memory `User` object (which is exactly what the test suite's
`signup_and_login(admin=True)` fixture does). That's an intentional Phase 2 gap, not an
oversight: admin provisioning is out of scope until there's a real user store to gate it
against.

### `app/api/routes/history.py`
`GET /history/rounds` and `GET /history/ledger`, both:

- Protected by `Depends(get_current_user)` (though the stub data isn't actually scoped to
  the caller yet — see below).
- Paginated via `limit` (default 20, max 100) and `offset` query params, returned inside
  a `PaginatedRounds`/`PaginatedLedger` envelope (`items`, `total`, `limit`, `offset`).
- Backed by two hardcoded lists (`_stub_rounds`, `_stub_ledger`) rather than real
  per-user queries — this is the one deliberately unfinished piece of Phase 2, called out
  in the roadmap as "swapped for Postgres in Phase 4." The pagination *mechanics*
  (slicing, `total`, query param validation) are real and tested; only the data source is
  fake.

### `app/main.py`
`create_app()` — the FastAPI application factory. Mounts all four Phase 2 routers
(`auth`, `users`, `tables`, `history`). No startup/shutdown hooks yet — those come in
Phase 4 (DB engine) and Phase 3/5 (Redis client, `TableManager`). A module-level `app`
instance is created for `uvicorn app.main:app` to pick up.

## Tests

### `tests/conftest.py`
- `_reset_in_memory_stores` (autouse) — clears `deps._users_by_id`,
  `deps._users_by_username`, and `tables_routes._tables` before *and* after every test.
  Necessary because Phase 2 persistence is plain module state shared across the whole
  test session; without this, tests would leak users/tables into each other.
- `client` — an `httpx.AsyncClient` wired directly to the FastAPI app via
  `ASGITransport` (no real network/socket involved).
- `signup_and_login` — a factory fixture returning an async `_make(username, password,
  admin=False)` helper that signs up a user, optionally flips `is_admin` directly on the
  stored `User` object, logs in, and returns `(headers, user_json)` ready to pass to
  authenticated requests.

### `tests/integration/test_auth.py`
Signup (success, duplicate-username `400`), login (success, wrong password `401`,
unknown user `401`), and `/users/me` (requires auth `401`, returns the right user,
rejects a garbage token).

### `tests/integration/test_tables.py`
Table list (starts empty), create (requires auth `401`, requires admin `403`, succeeds
and shows up in the list for an admin), get-by-id (`200` / `404`), and both history
endpoints (require auth, and correctly apply `limit`/`offset` against the stub data).

All 18 tests pass:

```
.venv/bin/python -m pytest tests/integration -v
```

## Known gaps / deferred to later phases

- **No real database.** Everything lives in module-level dicts/lists — restarting the
  process loses all users and tables. This is by design for Phase 2; Phase 4 introduces
  SQLAlchemy models + Alembic migrations.
- **History is stub data**, not scoped per-user despite the auth dependency being
  present.
- **No admin-provisioning endpoint.** `is_admin` is untestable from the outside; only
  test code (or a future admin-bootstrap mechanism) can set it.
- **Stale `# TODO` comments** remain in `auth.py`, `tables.py`, and `deps.py` describing
  work that's actually already done — worth a cleanup pass but harmless.
