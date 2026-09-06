"""WebSocket endpoint: accept/authenticate a connection, then route events to the
owning TableActor's queue and relay broadcasts back out.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter

from app.api import deps
from app.api.routes import tables as tables_routes
from app.api.ws.schemas import ClientEvent
from app.cache import redis_client
from app.db.session import SessionLocal
from app.engine.rules import TableRules
from app.tables.table_manager import table_manager

router = APIRouter()


@router.websocket("/ws/tables/{table_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: str, token: str):
    await websocket.accept()
    client_event_adapter = TypeAdapter(ClientEvent)

    try:
        user_id = deps.decode_access_token(token)
        sid = deps.decode_session_id(token)
    except ValueError:
        await websocket.close(code=4401)
        return

    cache = table_manager.redis
    if cache is not None and not await redis_client.session_is_active(cache, sid):
        await websocket.close(code=4401)
        return

    async with SessionLocal() as session:
        curr_table = await tables_routes.get_table_by_id(session, table_id)
    if curr_table is None:
        await websocket.close(code=4404)
        return

    rules = TableRules(min_bet=curr_table.min_bet, max_bet=curr_table.max_bet)
    actor = await table_manager.get_or_create(table_id, rules)
    actor.register(websocket)

    try:
        while True:
            raw = await websocket.receive_json()
            event = client_event_adapter.validate_python(raw)
            if event.type == "ping":
                # Doesn't touch table state, so it can be answered inline.
                await actor.handle_ping(websocket)
            else:
                # "join_table" / "sit" / "place_bet" / "action" / "leave_table"
                await actor.queue.put((event.type, user_id, event, websocket))
    except WebSocketDisconnect:
        actor.unregister(websocket)
