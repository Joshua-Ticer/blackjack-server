"""Async SQLAlchemy engine/session factory.

TODO:
- engine = create_async_engine(settings.database_url)
- async_sessionmaker bound to that engine
- an async generator suitable for FastAPI's Depends() (see api/deps.py)
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=True,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
