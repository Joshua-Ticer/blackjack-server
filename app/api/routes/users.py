"""Current-user profile and chip balance."""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

# TODO: GET /users/me  -- profile + chip_balance (derived from ledger)
