"""Signup / login / token issuance."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

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
from app.db.session import SessionLocal

router = APIRouter(prefix="/auth", tags=["auth"])


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

_argon2_concurrency = asyncio.Semaphore(os.cpu_count() or 4)


async def _hash_password(password: str) -> str:
    async with _argon2_concurrency:
        return await run_in_threadpool(pwd_context.hash, password)


async def _verify_password(password: str, hashed: str) -> bool:
    async with _argon2_concurrency:
        return await run_in_threadpool(pwd_context.verify, password, hashed)


@router.post("/signup", response_model=UserPublic)
async def signup(body: SignupRequest) -> User:
    async with SessionLocal() as db:
        if await get_user_by_username(db, body.username) is not None:
            raise HTTPException(status_code=400, detail="Username already taken")

    hashed = await _hash_password(body.password)

    async with SessionLocal() as db:
        return await create_user(db, body.username, hashed)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    cache: Redis | None = Depends(get_cache),
) -> TokenResponse:
    async with SessionLocal() as db:
        user = await get_user_by_username(db, form_data.username)

    valid = user is not None and await _verify_password(
        form_data.password, user.hashed_password
    )
    if not valid:
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
