"""Declarative base / metadata for ORM models.

Schema is created via Base.metadata.create_all() on startup (see app/main.py) rather
than migrations -- fine for a project with no production data to preserve; drop the
docker volume and restart if the schema changes during development.

TODO:
- class Base(DeclarativeBase): ...
- import every model module here so create_all() can discover them
"""
