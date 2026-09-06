from uuid import uuid4

from app.engine.rules import TableRules
from app.tables.table_manager import table_manager

BET_AMOUNT = 10


def _connect(ws_client, table_id, token):
    return ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}")


async def test_actor_crash_mid_turn_restores_from_redis_snapshot(
    client, table_and_token, ws_client, seed_table_manager
):
    table_id, token, player = table_and_token
    seed_table_manager(
        TableRules(
            min_bet=5, max_bet=500, betting_window_seconds=0.05, turn_timeout_seconds=30
        ),
        seed=10,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        ws.receive_json()

        ws.send_json({"type": "sit"})
        ws.receive_json()

        ws.send_json(
            {"type": "place_bet", "amount": BET_AMOUNT, "action_id": str(uuid4())}
        )
        ws.receive_json()

        dealt = ws.receive_json()
        assert dealt["lobby_state"] == "player_turns"
        pre_crash_hand = dealt["seats"][0]["hands"][0]
        pre_crash_dealer_upcard = dealt["dealer_hand"]

        ws.receive_json()  # player_turn

        table_manager.drop_local(table_id)

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()

        assert snapshot["lobby_state"] == "player_turns"
        assert snapshot["seats"][0]["player_id"] == player["id"]
        assert snapshot["seats"][0]["hands"][0] == pre_crash_hand
        assert snapshot["seats"][0]["bets"] == [BET_AMOUNT]
        assert snapshot["dealer_hand"] == pre_crash_dealer_upcard

        ws.send_json({"type": "action", "action": "stand", "action_id": str(uuid4())})
        delta = ws.receive_json()
        assert delta["type"] == "state_delta"

        result = ws.receive_json()
        assert result["type"] == "round_result"
        assert result["results"][0]["outcome"] == "win"

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["chip_balance"] == 10000 + BET_AMOUNT
