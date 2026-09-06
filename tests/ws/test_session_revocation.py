import pytest
from starlette.websockets import WebSocketDisconnect


async def test_websocket_rejects_a_logged_out_session(
    client, table_and_token, ws_client
):
    table_id, token, _ = table_and_token

    logout = await client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout.status_code == 200

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}") as ws:
            ws.receive_json()

    assert exc_info.value.code == 4401


async def test_websocket_accepts_a_still_active_session(
    client, table_and_token, ws_client
):
    table_id, token, _ = table_and_token

    with ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}") as ws:
        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()

    assert snapshot["type"] == "table_state"
