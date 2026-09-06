"""Load test: N virtual players logging into pre-seeded accounts, sitting at a
table, and playing round after round of blackjack over real WebSocket
connections.

Run against the Dockerized "prod-like" stack, not a laptop dev server:

    docker compose -f docker/docker-compose.yml up -d
    uv run python tests/load/seed.py --tables 20 --players 150
    uv run locust -f tests/load/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 and pick a user count / spawn rate. Login
still verifies one Argon2 hash per user (Argon2 verify costs the same as the
hash it's checking against -- there's no cheaper way to check it), but the
hash itself is computed once at seed time instead of once per locust user, so
100 concurrent logins measure the WS gateway, not 100x Argon2. Seat capacity
is 6/table, so seed at least ceil(peak_users / 6) tables and at least as many
player accounts as peak concurrent users, or users queue up waiting for a seat
that never opens. Table selection reads tables.json and username assignment
wraps modulo players.json's count (both written by seed.py -- a locust user
that gets respawned after a failed on_start reuses an existing account rather
than rolling past the seeded pool into logins that can never succeed) -- re-run
seed.py before every fresh locust run.

To spread users across multiple app instances sharing the same Redis/Postgres
(each instance then only has to service a fraction of the concurrent
WebSocket connections), set LOCUST_APP_HOSTS to a comma-separated list --
each user picks one at random, independently of its table assignment, so
tables end up genuinely shared across instances via the relay in
app/tables/table_manager.py rather than each table's users landing on a
single instance:

    LOCUST_APP_HOSTS=http://localhost:8000,http://localhost:8001 \
        uv run locust -f tests/load/locustfile.py --host http://localhost:8000

Reported request names:
  ws_join        -- connect + join_table + sit
  ws_place_bet   -- place_bet -> this player's own bet_placed delta
  ws_action      -- hit/stand -> this player's own action_applied delta
  ws_round       -- betting_open -> round_result, the whole hand end to end
"""

import itertools
import json
import os
import random
import time
from pathlib import Path
from uuid import uuid4

import gevent
import websocket
from locust import HttpUser, between, events, task
from locust.exception import StopUser

BET_AMOUNT = 5
JOIN_TIMEOUT = 60
BETTING_TIMEOUT = 60
ACTION_TIMEOUT = 60
ROUND_TIMEOUT = 200

PLAYER_USERNAME_PREFIX = "loadtest_player_"
PLAYER_PASSWORD = "loadtest-player-pw"
MANIFEST_PATH = Path(__file__).parent / "tables.json"
PLAYERS_MANIFEST_PATH = Path(__file__).parent / "players.json"

_app_hosts = [h.strip() for h in os.environ.get("LOCUST_APP_HOSTS", "").split(",") if h.strip()]

_player_index = itertools.count()
_table_ids: list[str] = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else []
_player_count: int = (
    json.loads(PLAYERS_MANIFEST_PATH.read_text()) if PLAYERS_MANIFEST_PATH.exists() else 0
)


class TableFullError(Exception):
    pass


class BlackjackPlayer(HttpUser):
    wait_time = between(0.5, 1)

    def on_start(self):
        index = next(_player_index)
        if not _player_count:
            raise StopUser("no players/players.json found -- run tests/load/seed.py first")
        self.username = f"{PLAYER_USERNAME_PREFIX}{index % _player_count:04d}"

        app_host = random.Random(index).choice(_app_hosts) if _app_hosts else self.host

        login = self.client.post(
            f"{app_host}/auth/login",
            data={"username": self.username, "password": PLAYER_PASSWORD},
            name="login",
        )
        if login.status_code != 200:
            raise StopUser(
                f"login failed for {self.username} -- run tests/load/seed.py "
                "with --players >= peak concurrent users"
            )
        self.token = login.json()["access_token"]

        me = self.client.get(
            f"{app_host}/users/me",
            headers={"Authorization": f"Bearer {self.token}"},
            name="me",
        )
        self.user_id = me.json()["id"]

        if not _table_ids:
            raise StopUser("no tables/tables.json found -- run tests/load/seed.py first")
        self.table_id = _table_ids[index % len(_table_ids)]

        scheme = "wss" if app_host.startswith("https") else "ws"
        host = app_host.split("://", 1)[1]
        self.ws = websocket.create_connection(
            f"{scheme}://{host}/ws/tables/{self.table_id}?token={self.token}",
            timeout=BETTING_TIMEOUT,
        )
        try:
            self._timed("ws_join", self._join_and_sit)
        except TableFullError as exc:
            raise StopUser(str(exc)) from exc

    def on_stop(self):
        ws = getattr(self, "ws", None)
        if ws is None:
            return
        try:
            self._send({"type": "leave_table"})
            self._wait_for("table_state", timeout=2)
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass

    def _join_and_sit(self) -> None:
        self._send({"type": "join_table"})
        self._wait_for("table_state", timeout=JOIN_TIMEOUT)
        self._send({"type": "sit"})
        try:
            msg = self._wait_for("error", "betting_open", timeout=2)
            if msg["type"] == "error":
                raise TableFullError(msg.get("detail", "sit rejected"))
        except TimeoutError:
            pass

    def _send(self, payload: dict) -> None:
        self.ws.send(json.dumps(payload))

    def _wait_for(self, *types: str, timeout: float, mine: bool = False):
        deadline = time.time() + timeout
        try:
            with gevent.Timeout(timeout, TimeoutError(f"never saw {types} within {timeout}s")):
                while time.time() < deadline:
                    raw = self.ws.recv()
                    if not raw:
                        raise websocket.WebSocketConnectionClosedException(
                            "connection closed"
                        )
                    msg = json.loads(raw)
                    if msg.get("type") not in types:
                        continue
                    if mine and msg.get("player_id") not in (None, self.user_id):
                        continue
                    return msg
        except websocket.WebSocketTimeoutException:
            pass
        raise TimeoutError(f"never saw {types} within {timeout}s")

    def _timed(self, name: str, fn) -> None:
        start = time.perf_counter()
        try:
            fn()
        except Exception as exc:
            events.request.fire(
                request_type="WS",
                name=name,
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=exc,
            )
            raise
        else:
            events.request.fire(
                request_type="WS",
                name=name,
                response_time=(time.perf_counter() - start) * 1000,
                response_length=0,
                exception=None,
            )

    @task
    def play_round(self):
        try:
            self._timed("ws_round", self._play_one_round)
        except (TimeoutError, TableFullError):
            pass

    def _play_one_round(self) -> None:
        self._wait_for("betting_open", timeout=BETTING_TIMEOUT)

        self._timed(
            "ws_place_bet",
            lambda: self._act_and_confirm(
                {"type": "place_bet", "amount": BET_AMOUNT, "action_id": str(uuid4())},
                "state_delta",
            ),
        )

        turn_or_result = self._wait_for(
            "player_turn", "round_result", timeout=BETTING_TIMEOUT + ACTION_TIMEOUT
        )
        if turn_or_result["type"] == "player_turn":
            self._timed(
                "ws_action",
                lambda: self._act_and_confirm(
                    {"type": "action", "action": "stand", "action_id": str(uuid4())},
                    "state_delta",
                ),
            )
            self._wait_for("round_result", timeout=ROUND_TIMEOUT)

    def _act_and_confirm(self, payload: dict, confirm_type: str) -> None:
        self._send(payload)
        self._wait_for(confirm_type, timeout=ACTION_TIMEOUT, mine=True)
