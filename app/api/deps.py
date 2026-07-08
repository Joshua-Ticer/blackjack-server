"""Shared FastAPI dependencies: DB session, current-user auth, etc.

TODO:
- get_db() -> AsyncGenerator[AsyncSession, None]   (yields a scoped session, see db/session.py)
- get_current_user(token: str = Depends(...)) -> User   (verifies JWT, loads user)
"""
