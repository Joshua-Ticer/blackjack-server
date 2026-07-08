"""Async SQLAlchemy engine/session factory.

TODO:
- engine = create_async_engine(settings.database_url)
- async_sessionmaker bound to that engine
- an async generator suitable for FastAPI's Depends() (see api/deps.py)
"""
