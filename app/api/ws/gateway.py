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
router = APIRouter()

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()

            await websocket.send_text(f"You said {data}")
    except WebSocketDisconnect:
        print("Client disconnected")
