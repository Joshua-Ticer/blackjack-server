from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    table_id: Mapped[UUID] = mapped_column(ForeignKey("tables.id"), index=True)
    deck_seed: Mapped[int | None] = mapped_column(default=None)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    table_id: Mapped[UUID] = mapped_column(ForeignKey("tables.id"), index=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("game_sessions.id"), index=True)
    dealer_hand: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default="in_progress")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(default=None)


class Participation(Base):
    __tablename__ = "participations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    seat_number: Mapped[int] = mapped_column()
    bet_amount: Mapped[int] = mapped_column()
    hands: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str | None] = mapped_column(default=None)
    payout: Mapped[int | None] = mapped_column(default=None)
