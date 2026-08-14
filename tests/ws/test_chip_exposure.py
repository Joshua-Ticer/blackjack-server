from uuid import uuid4

from app.engine.rules import TableRules

RULES = TableRules(
    min_bet=5, max_bet=10_000, betting_window_seconds=0.05, turn_timeout_seconds=5
)
PAIR_SEED = 68


def _connect(ws_client, table_id, token):
    return ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}")


def _play_to_turn(ws, amount):
    ws.send_json({"type": "join_table"})
    ws.receive_json()
    ws.send_json({"type": "sit"})
    ws.receive_json()
    ws.send_json({"type": "place_bet", "amount": amount, "action_id": str(uuid4())})
    ws.receive_json()
    ws.receive_json()
    turn = ws.receive_json()
    assert turn["type"] == "player_turn", turn
    return turn


async def test_split_offered_when_the_balance_covers_it(
    table_and_token, ws_client, seed_table_manager
):
    table_id, token, _player = table_and_token
    seed_table_manager(RULES, seed=PAIR_SEED)

    with _connect(ws_client, table_id, token) as ws:
        turn = _play_to_turn(ws, 4_000)
        assert "split" in turn["legal_actions"]
        assert "double" in turn["legal_actions"]


async def test_split_withheld_when_the_balance_cannot_cover_it(
    table_and_token, ws_client, seed_table_manager
):
    table_id, token, _player = table_and_token
    seed_table_manager(RULES, seed=PAIR_SEED)

    with _connect(ws_client, table_id, token) as ws:
        turn = _play_to_turn(ws, 8_000)
        assert "split" not in turn["legal_actions"]
        assert "double" not in turn["legal_actions"]
        assert "hit" in turn["legal_actions"]
        assert "stand" in turn["legal_actions"]


async def test_unaffordable_split_is_rejected_even_if_the_client_sends_it(
    table_and_token, ws_client, seed_table_manager
):
    table_id, token, _player = table_and_token
    seed_table_manager(RULES, seed=PAIR_SEED)

    with _connect(ws_client, table_id, token) as ws:
        _play_to_turn(ws, 8_000)

        ws.send_json({"type": "action", "action": "split", "action_id": str(uuid4())})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "insufficient chips" in error["detail"]

        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()
        seat = snapshot["seats"][0]
        assert len(seat["hands"]) == 1
        assert seat["bets"] == [8_000]


async def test_affordable_split_produces_two_hands_and_two_bets(
    table_and_token, ws_client, seed_table_manager
):
    table_id, token, _player = table_and_token
    seed_table_manager(RULES, seed=PAIR_SEED)

    with _connect(ws_client, table_id, token) as ws:
        _play_to_turn(ws, 4_000)

        ws.send_json({"type": "action", "action": "split", "action_id": str(uuid4())})

        delta = ws.receive_json()
        assert delta["type"] == "state_delta"
        assert delta["change"] == "action_applied"

        snapshot = ws.receive_json()
        assert snapshot["type"] == "table_state"
        seat = snapshot["seats"][0]
        assert len(seat["hands"]) == 2
        assert seat["bets"] == [4_000, 4_000]
        assert all(len(hand) == 2 for hand in seat["hands"])
