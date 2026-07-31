"""Adversarial concurrency tests: prove the single-writer-per-table design and
`action_id` dedup hold even when a client fires two identical messages
back-to-back, before the first has necessarily been processed by the actor's
`run()` loop.

Both tests check the *final* server-side state via a fresh `join_table`
snapshot rather than counting/ordering live broadcasts -- `join_table` and
`ping` bypass the queue and are handled directly by the gateway, so their
timing relative to the queued actions isn't guaranteed. Correct dedup is a
synchronous no-op with no side effects at all, so it doesn't matter whether
the duplicate has already been (not-)processed by the time we check; a broken
dedup would show up in the final state regardless of timing.
"""

from uuid import uuid4

from app.engine.rules import TableRules


def _connect(ws_client, table_id, token):
    return ws_client.websocket_connect(f"/ws/tables/{table_id}?token={token}")


async def test_duplicate_hit_action_id_applies_once(table_and_token, ws_client, seed_table_manager):
    table_id, token, _player = table_and_token
    # seed 2: player's initial 2 cards total 10, first hit lands a 10 (total 20,
    # neither bust nor blackjack) -- see tests/ws/conftest.py for how the seed
    # reaches the actor.
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=0.05, turn_timeout_seconds=5),
        seed=2,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        ws.receive_json()  # idle snapshot

        ws.send_json({"type": "sit"})
        ws.receive_json()  # betting_open

        ws.send_json({"type": "place_bet", "amount": 10, "action_id": str(uuid4())})

        ws.receive_json()  # post-deal table_state
        turn = ws.receive_json()
        assert turn["type"] == "player_turn"
        assert "hit" in turn["legal_actions"]

        hit_id = str(uuid4())
        hit_event = {"type": "action", "action": "hit", "action_id": hit_id}
        ws.send_json(hit_event)
        ws.send_json(hit_event)  # exact duplicate, sent before the first can be handled

        # side effects of the one real hit: a state_delta for the card dealt,
        # then a fresh player_turn since the hand is still alive
        delta = ws.receive_json()
        assert delta["type"] == "state_delta"
        assert delta["change"] == "action_applied"
        assert len(delta["detail"]["hand"]) == 3  # 2 initial cards + exactly one hit

        next_turn = ws.receive_json()
        assert next_turn["type"] == "player_turn"

        # confirm the final state directly: if the duplicate had double-applied,
        # this would show a 4th card (or a bust/settlement cascade) instead
        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()
        assert snapshot["type"] == "table_state"
        assert len(snapshot["seats"][0]["hands"][0]) == 3


async def test_duplicate_place_bet_action_id_applies_once(table_and_token, ws_client, seed_table_manager):
    table_id, token, _player = table_and_token
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=5, turn_timeout_seconds=5),
        seed=1,
    )

    with _connect(ws_client, table_id, token) as ws:
        ws.send_json({"type": "join_table"})
        ws.receive_json()  # idle snapshot

        ws.send_json({"type": "sit"})
        ws.receive_json()  # betting_open

        bet_id = str(uuid4())
        ws.send_json({"type": "place_bet", "amount": 10, "action_id": bet_id})
        ws.send_json({"type": "place_bet", "amount": 999, "action_id": bet_id})  # dup id, different amount

        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()
        assert snapshot["type"] == "table_state"
        assert snapshot["seats"][0]["bets"] == [10]
