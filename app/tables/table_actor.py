"""Single-writer-per-table actor: one asyncio task processes this table's event queue
serially, so no explicit locking is needed within a process -- see docs/adr/ for the
single-writer-per-table decision.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import WebSocket
from pydantic import TypeAdapter
from redis.asyncio import Redis
from sqlalchemy import select

from app.api import deps
from app.api.ws.schemas import (
    BettingOpen,
    ClientEvent,
    ErrorMsg,
    PlaceBet,
    PlayerAction,
    PlayerTurn,
    Pong,
    RoundResultMsg,
    SeatView,
    ServerEvent,
    SettlementItem,
    StateDelta,
    TableStateMsg,
)
from app.cache import redis_client as cache
from app.db.session import SessionLocal
from app.engine.card import Card
from app.engine.deck import Shoe
from app.engine.hand import Hand
from app.engine.round import InvalidBetError, Round, RoundError, Seat, SeatNotFoundError
from app.engine.rules import Action, TableRules
from app.engine.state_machine import StateMachine, TableEvent, TableState
from app.models.round import GameSession, Participation
from app.models.round import Round as RoundModel
from app.models.user import User
from app.services import settlement_service

_client_event_adapter = TypeAdapter(ClientEvent)


class TableActor:
    def __init__(self, table_id, rules, seed=None, redis: Redis | None = None):
        self.sm = StateMachine()
        self.round: Round | None = None
        self.shoe: Shoe | None = None
        self.session_id: UUID | None = None
        self.round_id: UUID | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.connections: dict[WebSocket, str | None] = {}  # ws -> player id
        self._seats: dict[str, int] = {}  # player id -> bet amount
        self._seen_actions: set = set()
        self._balances: dict[str, int] = {}
        self._version = 0
        self._turn_seq = 0
        self.table_id = table_id
        self.seed = seed
        self.rules: TableRules = rules
        self.redis = redis
        self._command_listener: asyncio.Task | None = None

    def register(self, ws: WebSocket):
        self.connections[ws] = None

    def unregister(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def handle_join(self, ws: WebSocket | None, player_id):
        if ws is not None:
            self.connections[ws] = player_id
        await self._deliver(self._build_snapshot(), player_id)

    async def handle_ping(self, ws: WebSocket):
        await ws.send_json(Pong().model_dump(mode="json"))

    async def start_command_listener(self) -> None:
        if self.redis is None or self._command_listener is not None:
            return
        ready = asyncio.Event()
        self._command_listener = asyncio.create_task(self._consume_commands(ready))
        await ready.wait()

    def stop(self) -> None:
        if self._command_listener is not None:
            self._command_listener.cancel()
            self._command_listener = None

    def pending_tasks(self) -> list[asyncio.Task]:
        return [self._command_listener] if self._command_listener is not None else []

    async def _consume_commands(self, ready: asyncio.Event) -> None:
        assert self.redis is not None
        channel = cache.COMMANDS_CHANNEL.format(table_id=self.table_id)
        async for message in cache.subscribe(self.redis, channel, ready=ready):
            event = _client_event_adapter.validate_python(message["event"])
            await self.queue.put((message["act"], message["player_id"], event, None))

    def _build_snapshot(self) -> TableStateMsg:
        lobby_state = self.sm.state.name.lower()
        if self.round is None:
            dealer_hand = []
            seats = [
                SeatView.from_lobby_bet(pid, bet) for pid, bet in self._seats.items()
            ]
        else:
            seats = [SeatView.from_seat(seat) for seat in self.round.seats]
            dealer_hand = self._dealer_view(self.round.dealer_hand, self.round.sm.state)

        return TableStateMsg(
            lobby_state=lobby_state,
            seats=seats,
            dealer_hand=dealer_hand,
            state_version=self._version,
        )

    def snapshot(self) -> dict:
        return {
            "sm_state": self.sm.state.name,
            "session_id": str(self.session_id) if self.session_id else None,
            "round_id": str(self.round_id) if self.round_id else None,
            "seats": self._seats,
            "seen_actions": [str(a) for a in self._seen_actions],
            "balances": self._balances,
            "version": self._version,
            "turn_seq": self._turn_seq,
            "shoe": self.shoe.snapshot() if self.shoe is not None else None,
            "round": self._serialize_round() if self.round is not None else None,
        }

    def restore(self, data: dict) -> None:
        self.sm.state = TableState[data["sm_state"]]
        self.session_id = UUID(data["session_id"]) if data["session_id"] else None
        self.round_id = UUID(data["round_id"]) if data["round_id"] else None
        self._seats = dict(data["seats"])
        self._seen_actions = {UUID(a) for a in data["seen_actions"]}
        self._balances = dict(data["balances"])
        self._version = data["version"]
        self._turn_seq = data["turn_seq"]

        if data["shoe"] is not None:
            self.shoe = Shoe.restore(
                data["shoe"]["num_decks"], data["shoe"]["remaining_cards"]
            )

        if data["round"] is not None:
            self.round = self._deserialize_round(data["round"])

        if self.sm.state == TableState.BETTING_OPEN:
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
        elif self.sm.state == TableState.PLAYER_TURNS and self.round is not None:
            for seat in self.round.seats:
                if not seat.is_hand_done(seat.active_hand_index):
                    self._schedule_turn_timeout(
                        seat.player_id, self.rules.turn_timeout_seconds
                    )
                    break

    def _deserialize_round(self, data: dict) -> Round:
        assert self.shoe is not None
        seats = [self._deserialize_seat(s) for s in data["seats"]]
        round_ = Round(self.shoe, self.rules, seats)
        round_.dealer_hand = Hand([Card.parse(c) for c in data["dealer_hand"]])
        round_.sm.state = TableState[data["state"]]
        round_._settled = round_.sm.state in (TableState.SETTLEMENT, TableState.IDLE)
        return round_

    def _deserialize_seat(self, data: dict) -> Seat:
        return Seat(
            player_id=data["player_id"],
            hands=[Hand([Card.parse(c) for c in hand]) for hand in data["hands"]],
            bets=list(data["bets"]),
            active_hand_index=data["active_hand_index"],
            surrendered_hands=set(data["surrendered_hands"]),
            standing_hands=set(data["standing_hands"]),
            doubled_hands=set(data["doubled_hands"]),
            split_aces_hands=set(data["split_aces_hands"]),
            total_splits=data["total_splits"],
        )

    def _serialize_round(self) -> dict:
        if self.round is None:
            raise RuntimeError("_serialize_round called but self.round is None")
        seats = [self._serialize_seat(seat) for seat in self.round.seats]
        dealer = [str(c) for c in self.round.dealer_hand.cards]
        return {
            "seats": seats,
            "dealer_hand": dealer,
            "state": self.round.sm.state.name,
        }

    def _serialize_seat(self, seat: Seat) -> dict:
        return {
            "player_id": seat.player_id,
            "hands": [[str(c) for c in hand.cards] for hand in seat.hands],
            "bets": list(seat.bets),
            "active_hand_index": seat.active_hand_index,
            "surrendered_hands": sorted(seat.surrendered_hands),
            "standing_hands": sorted(seat.standing_hands),
            "doubled_hands": sorted(seat.doubled_hands),
            "split_aces_hands": sorted(seat.split_aces_hands),
            "total_splits": seat.total_splits,
        }

    def _dealer_view(self, dealer_hand: Hand, lobby_state) -> list[str]:
        cards = [f"{c.rank.value}{c.suit.value}" for c in dealer_hand.cards]
        if lobby_state in (TableState.DEALER_TURN, TableState.SETTLEMENT):
            return cards
        return cards[:1]

    async def run(self):
        while True:
            act, player_id, event, ws = await self.queue.get()
            try:
                if act == "join_table":
                    # Queued rather than served straight from the gateway: a snapshot
                    # read must not overtake writes this client already sent, and all
                    # table-state access belongs to the single writer.
                    await self.handle_join(ws, player_id)
                elif act == "sit":
                    await self._handle_sit(player_id)
                elif act == "place_bet":
                    await self._handle_place_bet(player_id, event)
                elif act == "close_betting":
                    await self._close_betting_and_deal()
                elif act == "action":
                    await self._handle_action(player_id, event)
                elif act == "auto_stand":
                    if event == self._turn_seq:
                        await self._handle_action(
                            player_id, PlayerAction(action="stand", action_id=uuid4())
                        )
                elif act == "leave_table":
                    await self._handle_leave(player_id)
            except RoundError as e:
                await self._send_error(player_id, str(e))

    async def _handle_sit(self, player_id: str):
        if len(self._seats) >= self.rules.max_seats:
            raise RoundError("Table is full!")

        self._seats[player_id] = 0
        if len(self._seats) == 1 and self.sm.state == TableState.IDLE:
            self.sm.fire(TableEvent.PLAYERS_SEATED)
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
            self._version += 1
            await self._broadcast(
                BettingOpen(
                    deadline=datetime.now()
                    + timedelta(seconds=self.rules.betting_window_seconds),
                    min_bet=self.rules.min_bet,
                    max_bet=self.rules.max_bet,
                    state_version=self._version,
                )
            )

    async def _handle_place_bet(self, player_id: str, event: PlaceBet):
        if event.action_id in self._seen_actions:
            return
        self._seen_actions.add(event.action_id)
        if self.sm.state != TableState.BETTING_OPEN:
            raise RoundError("betting is closed")

        if not (self.rules.min_bet <= event.amount <= self.rules.max_bet):
            raise InvalidBetError(
                f"bet must be in between {self.rules.min_bet} and {self.rules.max_bet}"
            )

        async with SessionLocal() as session:
            user = await deps.get_user_by_id(session, player_id)
        if user is None:
            raise RoundError(f"unknown player {player_id}")
        if user.chip_balance < event.amount:
            raise InvalidBetError("insufficient chip count")

        self._seats[player_id] = event.amount
        self._version += 1
        await self._broadcast(
            StateDelta(
                change="bet_placed",
                player_id=player_id,
                detail={"amount": event.amount},
                state_version=self._version,
            )
        )

    def _affordable(self, seat: Seat, actions: set[Action]) -> set[Action]:
        headroom = self._balances.get(seat.player_id, 0) - sum(seat.bets)
        if headroom >= seat.bets[seat.active_hand_index]:
            return actions
        return actions - {Action.SPLIT, Action.DOUBLE}

    async def _handle_action(self, player_id, event: PlayerAction):
        if event.state_version is not None and event.state_version != self._version:
            return
        if event.action_id in self._seen_actions:
            return
        self._seen_actions.add(event.action_id)
        if self.round is None:
            raise RoundError("no round in progress")

        seat = self.round._get_seat(player_id)
        index = seat.active_hand_index

        action = Action(event.action)
        if action not in self._affordable(
            seat, self.round.legal_actions_for(player_id)
        ):
            raise RoundError("insufficient chips for that action")

        hands_before = len(seat.hands)
        self.round.player_action(player_id, action)
        self._version += 1
        await self._broadcast(
            StateDelta(
                change="action_applied",
                player_id=player_id,
                hand_index=index,
                detail={
                    "action": event.action,
                    "hand": [
                        f"{c.rank.value}{c.suit.value}" for c in seat.hands[index].cards
                    ],
                },
                state_version=self._version,
            )
        )

        if len(seat.hands) != hands_before:
            self._version += 1
            await self._broadcast(self._build_snapshot())

        if self.round.all_seats_done():
            await self._run_dealer_and_settle()
        else:
            await self._advance_turns()

    async def _handle_leave(self, player_id: str):
        if self.round is not None:
            try:
                seat = self.round._get_seat(player_id)
            except SeatNotFoundError:
                seat = None

            if seat is not None and not seat.all_hands_done():
                raise RoundError("cannot leave mid-round")

        self._seats.pop(player_id, None)
        self._version += 1
        await self._broadcast(self._build_snapshot())

    async def _ensure_shoe(self) -> Shoe:
        if self.shoe is not None and not self.shoe.needs_shuffle(
            self.rules.penetration
        ):
            return self.shoe

        async with SessionLocal() as session:
            async with session.begin():
                if self.session_id is not None:
                    old_session = await session.get(GameSession, self.session_id)
                    if old_session is not None:
                        old_session.ended_at = datetime.now(UTC).replace(tzinfo=None)

                new_session = GameSession(table_id=self.table_id, deck_seed=self.seed)
                session.add(new_session)
                await session.flush()
                self.session_id = new_session.id

        self.shoe = Shoe(seed=self.seed)
        return self.shoe

    async def _close_betting_and_deal(self):
        if self.sm.state != TableState.BETTING_OPEN:
            return  # already closed by the other trigger (timer vs. all-bets-in race)

        seated = [(pid, bet) for pid, bet in self._seats.items() if bet > 0]
        if not seated:
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
            self._version += 1
            await self._broadcast(
                BettingOpen(
                    deadline=datetime.now()
                    + timedelta(seconds=self.rules.betting_window_seconds),
                    min_bet=self.rules.min_bet,
                    max_bet=self.rules.max_bet,
                    state_version=self._version,
                )
            )
            return

        self.sm.fire(TableEvent.BETS_LOCKED)
        shoe = await self._ensure_shoe()
        seats = [Seat(player_id=pid, bets=[bet]) for pid, bet in seated]
        self.round = Round(shoe, self.rules, seats)
        self.round.deal_initial()

        async with SessionLocal() as session:
            pids = [pid for pid, _ in seated]
            users = (
                await session.execute(select(User).where(User.id.in_(pids)))
            ).scalars().all()
            balances_by_id = {str(u.id): u.chip_balance for u in users}
            for pid, _ in seated:
                self._balances[pid] = balances_by_id.get(pid, 0)

        async with SessionLocal() as session:
            async with session.begin():
                round_row = RoundModel(
                    table_id=self.table_id, session_id=self.session_id
                )
                session.add(round_row)
                await session.flush()
                self.round_id = round_row.id

                for seat_number, (pid, bet) in enumerate(seated):
                    session.add(
                        Participation(
                            round_id=self.round_id,
                            user_id=pid,
                            seat_number=seat_number,
                            bet_amount=bet,
                        )
                    )

        self.sm.fire(TableEvent.START_DEAL)
        self.sm.fire(TableEvent.DEAL_COMPLETE)

        self._version += 1
        await self._broadcast(self._build_snapshot())

        await self._advance_turns()

    async def _advance_turns(self):
        if self.round is None:
            raise RoundError("no round in progress")
        if self.round.all_seats_done():
            await self._run_dealer_and_settle()
            return

        for seat in self.round.seats:
            index = seat.active_hand_index
            if seat.is_hand_done(index):
                continue

            actions = self._affordable(
                seat, self.round.legal_actions_for(seat.player_id)
            )
            self._version += 1
            await self._broadcast_to_player(
                PlayerTurn(
                    player_id=seat.player_id,
                    hand_index=index,
                    legal_actions=[a.value for a in actions],
                    deadline=datetime.now()
                    + timedelta(seconds=self.rules.turn_timeout_seconds),
                    state_version=self._version,
                ),
                seat.player_id,
            )
            self._schedule_turn_timeout(seat.player_id, self.rules.turn_timeout_seconds)
            return

    async def _run_dealer_and_settle(self):
        if self.round is None or self.round_id is None:
            raise RoundError("no round in progress")

        self._turn_seq += 1
        self.sm.fire(TableEvent.ALL_PLAYERS_DONE)
        self.round.advance_to_dealer_turn()
        self.sm.fire(TableEvent.DEALER_DONE)
        results = self.round.settle()

        balances = await settlement_service.settle_round(
            self.round_id, results, self.round.seats
        )

        items = [
            SettlementItem(
                player_id=r.player_id,
                hand_index=r.hand_index,
                outcome=r.outcome.value,
                bet=r.bet,
                payout=r.payout,
                net=r.net,
                balance_after=balances.get(r.player_id, 0),
            )
            for r in results
        ]

        self._version += 1
        await self._broadcast(
            RoundResultMsg(
                results=items,
                dealer_hand=[str(c) for c in self.round.dealer_hand.cards],
                state_version=self._version,
            )
        )
        await self._reset_for_next_round()

    async def _reset_for_next_round(self):
        self.round = None
        self.round_id = None
        self._seen_actions.clear()
        self._balances.clear()
        for pid in self._seats:
            self._seats[pid] = 0

        self.sm.fire(TableEvent.SETTLED)  # -> IDLE
        self._version += 1

        if self._seats:
            self.sm.fire(TableEvent.PLAYERS_SEATED)  # -> BETTING_OPEN again
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
            await self._broadcast(
                BettingOpen(
                    deadline=datetime.now()
                    + timedelta(seconds=self.rules.betting_window_seconds),
                    min_bet=self.rules.min_bet,
                    max_bet=self.rules.max_bet,
                    state_version=self._version,
                )
            )
        else:
            await self._broadcast(self._build_snapshot())

    def _schedule_betting_timeout(self, deadline_seconds):
        loop = asyncio.get_running_loop()
        loop.call_later(
            deadline_seconds,
            lambda: self.queue.put_nowait(("close_betting", None, None, None)),
        )

    def _schedule_turn_timeout(self, player_id, deadline_seconds):
        loop = asyncio.get_running_loop()
        self._turn_seq += 1
        seq = self._turn_seq
        loop.call_later(
            deadline_seconds,
            lambda: self.queue.put_nowait(("auto_stand", player_id, seq, None)),
        )

    async def _send_error(self, player_id: str, detail: str):
        await self._deliver(ErrorMsg(detail=detail), player_id)

    async def _broadcast(self, table_state: ServerEvent):
        dead_ws = []
        for ws in self.connections:
            try:
                await ws.send_json(table_state.model_dump(mode="json"))
            except Exception:
                dead_ws.append(ws)

        for ws in dead_ws:
            self.unregister(ws)

        await self._publish_event(table_state, target=None)
        await self._persist()

    async def _broadcast_to_player(self, table_state: ServerEvent, player_id):
        await self._deliver(table_state, player_id)

    async def _deliver(self, table_state: ServerEvent, player_id: str) -> None:
        for ws, pid in list(self.connections.items()):
            if pid == player_id:
                try:
                    await ws.send_json(table_state.model_dump(mode="json"))
                except Exception:
                    self.unregister(ws)
                break

        await self._publish_event(table_state, target=player_id)
        await self._persist()

    async def _publish_event(
        self, table_state: ServerEvent, target: str | None
    ) -> None:
        if self.redis is None:
            return
        channel = cache.EVENTS_CHANNEL.format(table_id=self.table_id)
        await cache.publish(
            self.redis,
            channel,
            {
                "target": target,
                "payload": table_state.model_dump(mode="json"),
            },
        )

    async def _persist(self) -> None:
        if self.redis is None:
            return
        await cache.set_snapshot(self.redis, self.table_id, self.snapshot())
