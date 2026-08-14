"""Registry of live TableActors; routes events to the right table's queue.

TODO:
- TableManager.get_or_create(table_id) -> TableActor
- TableManager.remove(table_id)
- (Phase 5) lease/ownership of a table id via a Redis lock, for multi-instance scale-out
"""
import asyncio

from app.tables.table_actor import TableActor


class TableManager:
    def __init__(self):
        self._actors: dict[str, TableActor] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def get_or_create(self, table_id, rules, seed=None) -> TableActor:
        actor = self._actors.get(table_id)
        if actor is None:
            actor = TableActor(table_id, rules, seed=seed)
            self._actors[table_id] = actor
            self._tasks[table_id] = asyncio.create_task(actor.run())
        return actor

    def remove(self, table_id):
        task = self._tasks.pop(table_id, None)
        if task is not None:
            task.cancel()
        self._actors.pop(table_id, None)


table_manager = TableManager()
