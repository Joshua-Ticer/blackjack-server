"""Table listing / admin-only creation."""

from fastapi import APIRouter

router = APIRouter(prefix="/tables", tags=["tables"])

# TODO: GET /tables         -- list open tables
# TODO: POST /tables        -- admin-only create
# TODO: GET /tables/{id}    -- table detail (seats, min/max bet, status)
