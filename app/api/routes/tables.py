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
    status: str = "open"

class TableCreate(BaseModel):
    name: str
    min_bet: int
    max_bet: int


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

def get_table_by_id(table_id: str) -> Table | None:
    for table in _tables:
        if table.id == table_id:
            return table
    return None

@router.get("/{table_id}", response_model=Table)
def get_table(table_id: str) -> Table:
    table = get_table_by_id(table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return table
