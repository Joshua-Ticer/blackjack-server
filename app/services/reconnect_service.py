from app.api.ws.schemas import TableStateMsg
from app.tables.table_actor import TableActor
from app.tables.table_manager import TableManager


async def resume(
    manager: TableManager, table_id: str, rules, seed=None
) -> TableStateMsg | None:
    actor = await manager.get_or_create(table_id, rules, seed=seed)
    if not isinstance(actor, TableActor):
        return None
    return actor._build_snapshot()
