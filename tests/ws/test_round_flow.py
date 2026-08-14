"""End-to-end WebSocket flow tests: a full round played through the real gateway
(join -> sit -> bet -> act -> settle), cross-checked against the REST
`/users/me` view so the WS layer and the Phase 2 REST layer are proven to agree
on the same underlying User state.

Shoe seed 10 (with the player standing on their initial hand) is a fixed,
pre-verified outcome: player 8D/KH (18) beats dealer 5C/2S/JD (17) for a
straight win -- see tests/ws/conftest.py for why the seed has to come in via a
monkeypatched `get_or_create` rather than the REST `Table` model.
"""

from uuid import uuid4

from app.engine.rules import TableRules

BET_AMOUNT = 10
STARTING_BALANCE = 10000


def _connect(ws_client, table_id, token):
    return ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}")


async def test_full_round_result_matches_users_me(
    client, table_and_token, ws_client, seed_table_manager
):
    table_id, token, player = table_and_token
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=0.05, turn_timeout_seconds=5),
        seed=10,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()
        assert snapshot["type"] == "table_state"
        assert snapshot["lobby_state"] == "idle"

        ws.send_json({"type": "sit"})
        betting_open = ws.receive_json()
        assert betting_open["type"] == "betting_open"

        ws.send_json({"type": "place_bet", "amount": BET_AMOUNT, "action_id": str(uuid4())})

        bet_ack = ws.receive_json()
        assert bet_ack["type"] == "state_delta"
        assert bet_ack["change"] == "bet_placed"
        assert bet_ack["detail"]["amount"] == BET_AMOUNT

        # betting_window_seconds (0.05s) elapses on its own -- the actor deals
        # and broadcasts the post-deal snapshot, then prompts our turn.
        dealt = ws.receive_json()
        assert dealt["type"] == "table_state"
        assert dealt["lobby_state"] == "player_turns"
        assert len(dealt["seats"][0]["hands"][0]) == 2

        turn = ws.receive_json()
        assert turn["type"] == "player_turn"
        assert turn["player_id"] == player["id"]

        ws.send_json({"type": "action", "action": "stand", "action_id": str(uuid4())})

        delta = ws.receive_json()
        assert delta["type"] == "state_delta"
        assert delta["change"] == "action_applied"

        result = ws.receive_json()
        assert result["type"] == "round_result"
        outcome = result["results"][0]
        assert outcome["outcome"] == "win"
        assert outcome["bet"] == BET_AMOUNT
        assert outcome["payout"] == BET_AMOUNT * 2
        assert outcome["net"] == BET_AMOUNT
        assert outcome["balance_after"] == STARTING_BALANCE + BET_AMOUNT

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["chip_balance"] == outcome["balance_after"]


async def test_disconnect_mid_turn_auto_stands_via_timeout(
    client, table_and_token, ws_client, seed_table_manager
):
    """A player who drops the connection mid-turn must not stall the round --
    the turn-timeout timer (independent of any live connection) has to fire the
    auto-stand and carry the round through to settlement regardless."""
    table_id, token, player = table_and_token
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=0.05, turn_timeout_seconds=0.1),
        seed=10,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        ws.receive_json()  # idle snapshot

        ws.send_json({"type": "sit"})
        ws.receive_json()  # betting_open

        ws.send_json({"type": "place_bet", "amount": BET_AMOUNT, "action_id": str(uuid4())})

        ws.receive_json()  # bet_placed delta
        ws.receive_json()  # post-deal table_state
        turn = ws.receive_json()
        assert turn["type"] == "player_turn"
        # deliberately disconnect here without acting -- exiting the `with`
        # block below closes the socket while it's still this player's turn

    import time

    time.sleep(0.5)  # let the 0.1s turn-timeout fire and settlement complete

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["chip_balance"] == STARTING_BALANCE + BET_AMOUNT
