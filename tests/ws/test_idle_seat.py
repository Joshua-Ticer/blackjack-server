from app.engine.rules import TableRules


def _connect(ws_client, table_id, token):
    return ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}")


async def test_an_unbet_seat_does_not_deal_a_round(
    table_and_token, ws_client, seed_table_manager
):
    table_id, token, _ = table_and_token
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=0.05, turn_timeout_seconds=5),
        seed=10,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        ws.receive_json()

        ws.send_json({"type": "sit"})
        betting_open = ws.receive_json()
        assert betting_open["type"] == "betting_open"

        next_betting_open = ws.receive_json()
        assert next_betting_open["type"] == "betting_open"
        assert next_betting_open["state_version"] > betting_open["state_version"]
