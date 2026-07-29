"""FastAPI application factory."""

from fastapi import FastAPI

from app.api.routes import auth, history, tables, users


def create_app() -> FastAPI:
    app = FastAPI(title="Blackjack Server")

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(tables.router)
    app.include_router(history.router)

    # Phase 2 uses an in-memory store (see api/deps.py) -- no DB startup hook yet.
    # TODO (Phase 4): startup hook -- run Base.metadata.create_all() against the async
    #       engine (see app/db/base.py, app/db/session.py) once Postgres is wired in.
    # TODO (Phase 3/5): startup/shutdown hooks for Redis client, TableManager.

    return app


app = create_app()
