"""Async SQLAlchemy engine/session factory."""

from typing import Any, AsyncGenerator
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from app.config import settings

_engine_kwargs: dict[str, Any] = {"echo": settings.app_env == "development"}

if settings.app_env == "test":
    # pytest-asyncio gives each test its own event loop, but asyncpg connections are
    # bound to the loop that opened them. Pooling would hand a connection from a
    # closed loop to the next test ("attached to a different loop"), so don't pool.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["pool_size"] = 3
    _engine_kwargs["max_overflow"] = 3

engine = create_async_engine(settings.database_url, **_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
