"""Table listing / admin-only creation."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import User, get_current_user

router = APIRouter(prefix="/tables", tags=["tables"])

class Table(BaseModel):
    id: str
    name: str
    min_bet: int
    max_bet: int
    max_seats: int
    status: str = "open"

class TableCreate(BaseModel):
    name: str
    min_bet: int
    max_bet: int
    max_seats: int


_tables: list[Table] = []

@router.get("", response_model=list[Table])
def list_tables() -> list[Table]:
    return _tables

@router.post("", response_model=Table)
def create_table(body: TableCreate, user: User = Depends(get_current_user)) -> Table:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    table = Table(id=str(uuid4()), **body.model_dump())
    _tables.append(table)
    return table

@router.get("/{table_id}", response_model=Table)
def get_table(table_id: str) -> Table:
    for table in _tables:
        if table.id == table_id:
            return table
    raise HTTPException(status_code=404, detail="Table not found")


# TODO: GET /tables         -- list open tables
# TODO: POST /tables        -- admin-only create
# TODO: GET /tables/{id}    -- table detail (seats, min/max bet, status)
