"""Registry of live TableActors; routes events to the right table's queue.

TODO:
- TableManager.get_or_create(table_id) -> TableActor
- TableManager.remove(table_id)
- (Phase 5) lease/ownership of a table id via a Redis lock, for multi-instance scale-out
"""
