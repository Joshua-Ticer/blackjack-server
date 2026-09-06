"""Table listing / admin-only creation."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, TypeAdapter
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import User, get_cache, get_current_user
from app.cache import redis_client
from app.db.session import get_session
from app.models.table import Table

router = APIRouter(prefix="/tables", tags=["tables"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
TABLE_LIST_TTL = 30


class TableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    min_bet: int
    max_bet: int
    status: str = "open"


class TableCreate(BaseModel):
    name: str
    min_bet: int
    max_bet: int
    max_seats: int = 6


_table_list_adapter = TypeAdapter(list[TableResponse])


@router.get("", response_model=list[TableResponse])
async def list_tables(
    db: DatabaseSession, cache: Redis | None = Depends(get_cache)
) -> list[TableResponse]:
    if cache is not None:
        cached = await redis_client.cache_get(cache, redis_client.TABLE_LIST_KEY)
        if cached is not None:
            return _table_list_adapter.validate_json(cached)

    result = await db.execute(select(Table))
    tables = [TableResponse.model_validate(t) for t in result.scalars().all()]

    if cache is not None:
        await redis_client.cache_set(
            cache,
            redis_client.TABLE_LIST_KEY,
            json.dumps([t.model_dump(mode="json") for t in tables]),
            ttl=TABLE_LIST_TTL,
        )
    return tables


@router.post("", response_model=TableResponse)
async def create_table(
    body: TableCreate,
    db: DatabaseSession,
    user: User = Depends(get_current_user),
    cache: Redis | None = Depends(get_cache),
) -> Table:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    table = Table(**body.model_dump())
    db.add(table)
    await db.commit()
    await db.refresh(table)

    if cache is not None:
        await redis_client.cache_delete(cache, redis_client.TABLE_LIST_KEY)

    return table


async def get_table_by_id(db: AsyncSession, table_id: str) -> Table | None:
    # A well-formed str binds fine to the UUID column, but a malformed one raises
    # ValueError/DataError down in asyncpg -- a 500 for what is really "not found".
    try:
        UUID(table_id)
    except ValueError:
        return None
    return await db.get(Table, table_id)


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(table_id: str, db: DatabaseSession) -> Table:
    table = await get_table_by_id(db, table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return table
