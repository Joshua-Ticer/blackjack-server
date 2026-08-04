"""Adversarial concurrency tests: prove the single-writer-per-table design and
`action_id` dedup hold even when a client fires two identical messages
back-to-back, before the first has necessarily been processed by the actor's
`run()` loop.

Both tests check the *final* server-side state via a fresh `join_table`
snapshot rather than reasoning about broadcast counts alone. `join_table` is
itself queued (only `ping` is answered inline by the gateway), so its snapshot
is guaranteed to observe every action sent before it -- which is precisely what
makes it a reliable read-your-writes probe here. Correct dedup is a synchronous
no-op with no side effects, so a broken dedup shows up in that final state
regardless of timing.
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

        ws.receive_json()  # bet_placed delta
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


async def test_another_player_leaving_does_not_void_pending_turn_timeout(
    client, table_and_token, ws_client, seed_table_manager, signup_and_login
):
    """A player leaving bumps state_version but must not invalidate the in-flight
    turn-timeout timer of whoever is on turn -- otherwise the auto-stand is silently
    dropped and the round hangs on that turn forever."""
    table_id, token, _player = table_and_token
    seed_table_manager(
        TableRules(min_bet=5, max_bet=500, betting_window_seconds=0.4, turn_timeout_seconds=0.2),
        seed=10,
    )
    leaver_headers, _leaver = await signup_and_login(username="leaver")
    leaver_token = leaver_headers["Authorization"].removeprefix("Bearer ")

    with _connect(ws_client, table_id, leaver_token) as ws_leaver:
        ws_leaver.send_json({"type": "join_table"})
        ws_leaver.receive_json()
        ws_leaver.send_json({"type": "sit"})

        with _connect(ws_client, table_id, token) as ws:
            ws.send_json({"type": "join_table"})
            ws.receive_json()
            ws.send_json({"type": "sit"})
            ws.send_json({"type": "place_bet", "amount": 10, "action_id": str(uuid4())})

            for _ in range(8):
                if ws.receive_json().get("type") == "player_turn":
                    break
            else:
                raise AssertionError("never reached player_turn")

            ws_leaver.send_json({"type": "leave_table"})
            ws_leaver.receive_json()

    import time

    time.sleep(0.8)

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["chip_balance"] == 10010


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

        # exactly one bet_placed ack: the duplicate is deduped before it can emit.
        # If dedup were broken there'd be a second ack for 999 ahead of the snapshot.
        ack = ws.receive_json()
        assert ack["type"] == "state_delta"
        assert ack["change"] == "bet_placed"
        assert ack["detail"]["amount"] == 10

        ws.send_json({"type": "join_table"})
        snapshot = ws.receive_json()
        assert snapshot["type"] == "table_state"
        assert snapshot["seats"][0]["bets"] == [10]
