"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, history, tables, users
from app.api.ws import gateway
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # TODO (Phase 3/5): startup/shutdown hooks for Redis client, TableManager.


def create_app() -> FastAPI:
    app = FastAPI(title="Blackjack Server", lifespan=lifespan)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(tables.router)
    app.include_router(history.router)
    app.include_router(gateway.router)

    return app


app = create_app()
