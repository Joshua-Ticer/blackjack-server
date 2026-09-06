"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, history, tables, users
from app.api.ws import gateway
from app.cache import redis_client
from app.db.base import Base
from app.db.session import engine
from app.tables.table_manager import table_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    owns_redis = redis_client.get_shared_client() is None
    redis = None
    if owns_redis:
        try:
            redis = await redis_client.get_redis()
        except redis_client.NETWORK_ERRORS:
            pass
        redis_client.set_shared_client(redis)
        table_manager.set_redis(redis)

    yield

    table_manager.shutdown_all()
    if owns_redis:
        table_manager.set_redis(None)
        redis_client.set_shared_client(None)
        if redis is not None:
            await redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Blackjack Server", lifespan=lifespan)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(tables.router)
    app.include_router(history.router)
    app.include_router(gateway.router)

    return app


app = create_app()
