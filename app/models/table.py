"""Table ORM model.

TODO fields: id, name, min_bet, max_bet, max_seats, status (open/closed), created_at
"""

from datetime import datetime
from app.db.base import Base
from uuid import UUID, uuid4

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import func


class Table(Base):
    __tablename__ = "tables"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(unique=True, index=True)
    min_bet: Mapped[int] = mapped_column()
    max_bet: Mapped[int] = mapped_column()
    max_seats: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())