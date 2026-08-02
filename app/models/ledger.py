from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    round_id: Mapped[UUID | None] = mapped_column(ForeignKey("rounds.id"), default=None)
    amount: Mapped[int] = mapped_column()
    type: Mapped[str] = mapped_column()
    balance_after: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
