"""Declarative base / metadata for ORM models.

Schema is created via Base.metadata.create_all() on startup (see app/main.py) rather
than migrations -- fine for a project with no production data to preserve; drop the
docker volume and restart if the schema changes during development.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


import app.models.ledger  # noqa: E402,F401
import app.models.round  # noqa: E402,F401
import app.models.table  # noqa: E402,F401
import app.models.user  # noqa: E402,F401
