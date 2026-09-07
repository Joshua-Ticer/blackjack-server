"""User ORM model.

chip_balance is a cached/reconciled column derived from LedgerEntry rows -- never
mutate it directly from game logic, see models/ledger.py.
"""

from app.db.base import Base
from uuid import UUID, uuid4
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column()
    chip_balance: Mapped[int] = mapped_column(default=10000)
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
