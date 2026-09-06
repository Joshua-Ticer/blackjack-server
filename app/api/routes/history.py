"""Paginated round/ledger history for the current user."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import User, get_current_user
from app.db.session import get_session
from app.models.ledger import LedgerEntry
from app.models.round import Participation, Round

router = APIRouter(prefix="/history", tags=["history"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


class RoundHistoryItem(BaseModel):
    round_id: str
    table_id: str
    outcome: str
    net: int


class LedgerHistoryItem(BaseModel):
    entry_id: str
    amount: int
    type: str
    balance_after: int


class PaginatedRounds(BaseModel):
    items: list[RoundHistoryItem]
    total: int
    limit: int
    offset: int


class PaginatedLedger(BaseModel):
    items: list[LedgerHistoryItem]
    total: int
    limit: int
    offset: int


@router.get("/rounds", response_model=PaginatedRounds)
async def get_round_history(
    db: DatabaseSession,
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedRounds:
    stmt = (
        select(Participation, Round.table_id)
        .join(Round, Participation.round_id == Round.id)
        .where(Participation.user_id == user.id)
        .order_by(Round.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    items = []
    for p, table_id in rows:
        net = await db.scalar(
            select(func.sum(LedgerEntry.amount)).where(
                LedgerEntry.round_id == p.round_id, LedgerEntry.user_id == user.id
            )
        )
        items.append(
            RoundHistoryItem(
                round_id=str(p.round_id),
                table_id=str(table_id),
                outcome=p.outcome or "",
                net=net or 0,
            )
        )
    total = await db.scalar(
        select(func.count())
        .select_from(Participation)
        .where(Participation.user_id == user.id)
    )
    return PaginatedRounds(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/ledger", response_model=PaginatedLedger)
async def get_ledger_history(
    db: DatabaseSession,
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedLedger:
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        LedgerHistoryItem(
            entry_id=str(row.id),
            amount=row.amount,
            type=row.type,
            balance_after=row.balance_after,
        )
        for row in rows
    ]
    total = await db.scalar(
        select(func.count())
        .select_from(LedgerEntry)
        .where(LedgerEntry.user_id == user.id)
    )
    return PaginatedLedger(items=items, total=total or 0, limit=limit, offset=offset)
