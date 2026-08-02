"""Paginated round/ledger history for the current user."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import User, get_current_user

router = APIRouter(prefix="/history", tags=["history"])


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


# Stub data -- Phase 4 replaces this with real per-user queries against
# Postgres (rounds/ledger tables), scoped by `user.id`.
_stub_rounds: list[RoundHistoryItem] = [
    RoundHistoryItem(round_id="r1", table_id="t1", outcome="win", net=20),
    RoundHistoryItem(round_id="r2", table_id="t1", outcome="loss", net=-10),
]
_stub_ledger: list[LedgerHistoryItem] = [
    LedgerHistoryItem(entry_id="l1", amount=-10, type="bet", balance_after=990),
    LedgerHistoryItem(entry_id="l2", amount=20, type="payout", balance_after=1010),
]


@router.get("/rounds", response_model=PaginatedRounds)
def get_round_history(
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedRounds:
    page = _stub_rounds[offset : offset + limit]
    return PaginatedRounds(items=page, total=len(_stub_rounds), limit=limit, offset=offset)


@router.get("/ledger", response_model=PaginatedLedger)
def get_ledger_history(
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedLedger:
    page = _stub_ledger[offset : offset + limit]
    return PaginatedLedger(items=page, total=len(_stub_ledger), limit=limit, offset=offset)
