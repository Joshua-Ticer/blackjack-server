"""Signup / login / token issuance."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict

from app.api.deps import User, create_user, get_user_by_username
from app.config import settings
from app.db.session import get_session


router = APIRouter(prefix="/auth", tags=["auth"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]

# TODO: POST /auth/signup  -- hash password (argon2), create User
# TODO: POST /auth/login   -- verify password, issue JWT

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
async def login(db: DatabaseSession, form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = await get_user_by_username(db, form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    token = jwt.encode(
        {"sub": str(user.id), "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return TokenResponse(access_token=token)
