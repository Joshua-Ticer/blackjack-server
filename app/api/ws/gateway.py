"""WebSocket endpoint: accept/authenticate a connection, then route events to the
owning TableActor's queue and relay broadcasts back out.

TODO:
- @router.websocket("/ws/tables/{table_id}")
- authenticate via session token (same auth as REST)
- on connect: register with TableManager, send full table_state snapshot
- on receive: validate against api/ws/schemas.py, enqueue onto the table's TableActor
- on disconnect: deregister; do not mutate table state directly from this handler
"""

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter

from app.api import deps
from app.api.routes import tables as tables_routes
from app.api.ws.schemas import ClientEvent
from app.engine.rules import TableRules
from app.tables.table_manager import table_manager

router = APIRouter()


@router.websocket("/ws/tables/{table_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: str, token: str):
    await websocket.accept()
    client_event_adapter = TypeAdapter(ClientEvent)
    
    try:
        user = deps.decode_access_token(token)
    except ValueError:
        await websocket.close(code=4401)
        return
    

    curr_table = tables_routes.get_table_by_id(table_id)
    if curr_table is None:
        await websocket.close(code=4404)
        return

    rules = TableRules(min_bet=curr_table.min_bet, max_bet=curr_table.max_bet)
    actor = table_manager.get_or_create(table_id, rules)
    actor.register(websocket)

    try: 
        while True:
            raw = await websocket.receive_json()
            event = client_event_adapter.validate_python(raw)
            if event.type == "join_table":
                await actor.handle_join(websocket, user.id)
            elif event.type == "ping":
                await actor.handle_ping(websocket)
            else:
                kind = event.type  # "sit" / "place_bet" / "action" / "leave_table"
                await actor.queue.put((kind, user.id, event))
    except WebSocketDisconnect:
        actor.unregister(websocket)

