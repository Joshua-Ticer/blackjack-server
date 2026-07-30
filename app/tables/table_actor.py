"""Single-writer-per-table actor: one asyncio task processes this table's event queue
serially, so no explicit locking is needed within a process -- see docs/adr/ for the
single-writer-per-table decision.

TODO:
- TableActor wrapping an asyncio.Queue + a run loop + the engine.Round it owns
- apply(event) -> broadcasts the resulting state_delta to connected clients
- snapshot() / restore()  -- periodic Redis-backed persistence for crash recovery (Phase 5)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict
from uuid import uuid4

from fastapi import WebSocket
from app.api import deps
from app.api.ws.schemas import BettingOpen, ErrorMsg, PlaceBet, PlayerAction, PlayerTurn, Pong, SeatView, ServerEvent, StateDelta, TableStateMsg
from app.engine.hand import Hand
from app.engine.deck import Shoe
from app.engine.round import InvalidBetError, Round, RoundError, Seat
from app.engine.rules import Action, TableRules
from app.engine.state_machine import StateMachine, TableEvent, TableState


class TableActor:
    def __init__(self, table_id, rules, seed=None):
        self.sm = StateMachine()
        self.round: Round | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.connections: Dict[WebSocket, str | None] = {} # ws -> player id
        self._seats: Dict[str, int] = {} # player id -> bet amount
        self._seen_actions: set = set()
        self._version = 0
        self.table_id = table_id
        self.seed = seed
        self.rules: TableRules = rules

    def register(self, ws: WebSocket):
        self.connections[ws] = None

    def unregister(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def handle_join(self, ws: WebSocket, player_id):
        self.connections[ws] = player_id
        snapshot = self._build_snapshot()
        await ws.send_json(snapshot.model_dump())

    async def handle_ping(self, ws: WebSocket):
        await ws.send_json(Pong().model_dump())

    def _build_snapshot(self) -> TableStateMsg:
        lobby_state = self.sm.state.name.lower()
        if self.round is None:
            dealer_hand = []
            seats = [SeatView.from_lobby_bet(pid, bet) for pid, bet in self._seats.items()]
        else:
            seats = [SeatView.from_seat(seat) for seat in self.round.seats]
            dealer_hand = self._dealer_view(self.round.dealer_hand, self.round.sm.state)

        return TableStateMsg(
        lobby_state=lobby_state,
        seats=seats,
        dealer_hand=dealer_hand,
        state_version=self._version,
    )

    def _dealer_view(self, dealer_hand: Hand, lobby_state) -> list[str]:
        cards = [f"{c.rank.value}{c.suit.value}" for c in dealer_hand.cards]
        if lobby_state in (TableState.DEALER_TURN, TableState.SETTLEMENT):
            return cards
        return cards[:1]

    async def run(self):
        while True:
            act, player_id, event = await self.queue.get()
            try:
                if act == "sit":
                    await self._handle_sit(player_id)
                elif act == "place_bet":
                    self._handle_place_bet(player_id, event)
                elif act == "close_betting":
                    await self._close_betting_and_deal()
                elif act == "action":
                    await self._handle_action(player_id, event)
            except RoundError as e:
                await self._send_error(player_id, str(e))

    async def _handle_sit(self, player_id: str):
        self._seats[player_id] = 0
        if len(self._seats) == 1 and self.sm.state == TableState.IDLE:
            self.sm.fire(TableEvent.PLAYERS_SEATED)
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
            self._version += 1
            await self._broadcast(BettingOpen(
                deadline=datetime.now() + timedelta(seconds=self.rules.betting_window_seconds),
                min_bet=self.rules.min_bet,
                max_bet=self.rules.max_bet,
                state_version=self._version,
            ))

    def _handle_place_bet(self, player_id: str, event: PlaceBet):
        if event.action_id in self._seen_actions:
            return
        self._seen_actions.add(event.action_id)

        if not (self.rules.min_bet <= event.amount <= self.rules.max_bet):
            raise InvalidBetError(f"bet must be in between {self.rules.min_bet} and {self.rules.max_bet}")

        user = deps.get_user_by_id(player_id)
        if user is None:
            raise RoundError(f"unknown player {player_id}")
        if user.chip_balance < event.amount:
            raise InvalidBetError("insufficient chip count")

        self._seats[player_id] = event.amount

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
        self.round.player_action(player_id, Action(event.action))
        self._version += 1
        await self._broadcast(StateDelta(
            change="action_applied",
            player_id=player_id,
            hand_index=index,
            detail={"action": event.action, "hand": [f"{c.rank.value}{c.suit.value}" for c in seat.hands[index].cards]},
            state_version=self._version,
        ))

        if self.round.all_seats_done():
            await self._run_dealer_and_settle()
        else:
            await self._advance_turns()

    async def _close_betting_and_deal(self):
        if self.sm.state != TableState.BETTING_OPEN:
            return  # already closed by the other trigger (timer vs. all-bets-in race)

        self.sm.fire(TableEvent.BETS_LOCKED)
        seats = [Seat(player_id=pid, bets=[bet]) for pid, bet in self._seats.items() if bet > 0]
        self.round = Round(Shoe(seed=self.seed), self.rules, seats)
        self.round.deal_initial()

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

            actions = self.round.legal_actions_for(seat.player_id)
            self._version += 1
            await self._broadcast_to_player(PlayerTurn(
                player_id=seat.player_id,
                hand_index=index,
                legal_actions=[a.value for a in actions],
                deadline=datetime.now() + timedelta(seconds=self.rules.turn_timeout_seconds),
                state_version=self._version,
            ), seat.player_id)
            self._schedule_turn_timeout(seat.player_id, self.rules.turn_timeout_seconds)
            return

    async def _reset_for_next_round(self):
        self.round = None
        self._seen_actions.clear()
        for pid in self._seats:
            self._seats[pid] = 0

        self.sm.fire(TableEvent.SETTLED)  # -> IDLE
        self._version += 1

        if self._seats:
            self.sm.fire(TableEvent.PLAYERS_SEATED)  # -> BETTING_OPEN again
            self._schedule_betting_timeout(self.rules.betting_window_seconds)
            await self._broadcast(BettingOpen(
                deadline=datetime.now() + timedelta(seconds=self.rules.betting_window_seconds),
                min_bet=self.rules.min_bet,
                max_bet=self.rules.max_bet,
                state_version=self._version,
            ))
        else:
            await self._broadcast(self._build_snapshot())


    def _schedule_betting_timeout(self, deadline_seconds):
        loop = asyncio.get_running_loop()
        loop.call_later(
            deadline_seconds,
            lambda: self.queue.put_nowait(("close_betting", None, None)),
        )

    def _schedule_turn_timeout(self, player_id, deadline_seconds):
        loop = asyncio.get_running_loop()
        version_at_send = self._version
        loop.call_later(
            deadline_seconds,
            lambda: self.queue.put_nowait(
                ("action", player_id, PlayerAction(action="stand", action_id=uuid4(), state_version=version_at_send))
            ),
        )

    async def _send_error(self, player_id: str, detail: str):
        for ws, pid in self.connections.items():
            if pid == player_id:
                await ws.send_json(ErrorMsg(detail=detail).model_dump())
                return

    async def _broadcast(self, table_state: ServerEvent):
        dead_ws = []
        for ws in self.connections:
            try:
                await ws.send_json(table_state.model_dump())
            except Exception:
                dead_ws.append(ws)

        for ws in dead_ws:
            self.unregister(ws)

    async def _broadcast_to_player(self, table_state: ServerEvent, player_id):    
        for ws, pid in self.connections.items():
            if pid == player_id:
                await ws.send_json(table_state.model_dump())
                return

