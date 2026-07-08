"""Paginated round/ledger history for the current user."""

from fastapi import APIRouter

router = APIRouter(prefix="/history", tags=["history"])

# TODO: GET /history/rounds       -- paginated past rounds for the current user
# TODO: GET /history/ledger       -- paginated ledger entries for the current user
