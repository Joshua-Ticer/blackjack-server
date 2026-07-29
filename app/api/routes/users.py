"""Current-user profile and chip balance."""

from fastapi import APIRouter, Depends

from app.api.deps import User, get_current_user
from app.api.routes.auth import UserPublic

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

# TODO: GET /users/me  -- profile + chip_balance (derived from ledger)
