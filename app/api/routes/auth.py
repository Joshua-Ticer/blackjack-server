"""Signup / login / token issuance."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    User,
    create_user,
    decode_session_id,
    get_cache,
    get_user_by_username,
    oauth2_scheme,
)
from app.cache import redis_client
from app.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


class SignupRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    chip_balance: int
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


@router.post("/signup", response_model=UserPublic)
async def signup(db: DatabaseSession, body: SignupRequest) -> User:
    if await get_user_by_username(db, body.username) is not None:
        raise HTTPException(status_code=400, detail="Username already taken")
    hashed = pwd_context.hash(body.password)
    return await create_user(db, body.username, hashed)


@router.post("/login", response_model=TokenResponse)
async def login(
    db: DatabaseSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
    cache: Redis | None = Depends(get_cache),
) -> TokenResponse:
    user = await get_user_by_username(db, form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    sid = str(uuid4())
    expire_minutes = settings.jwt_expire_minutes
    expire = datetime.now(UTC) + timedelta(minutes=expire_minutes)
    token = jwt.encode(
        {"sub": str(user.id), "sid": sid, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    if cache is not None:
        await redis_client.create_session(
            cache, sid, str(user.id), ttl=expire_minutes * 60
        )

    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    cache: Redis | None = Depends(get_cache),
) -> dict:
    if cache is not None:
        try:
            sid = decode_session_id(token)
        except ValueError:
            raise HTTPException(
                status_code=401, detail="Could not validate credentials"
            )
        await redis_client.delete_session(cache, sid)

    return {"detail": "logged out"}
