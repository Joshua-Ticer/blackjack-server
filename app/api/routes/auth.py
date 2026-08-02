"""Signup / login / token issuance."""

from fastapi import APIRouter
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel

from app.api.deps import User, create_user, get_user_by_username
from app.config import settings


router = APIRouter(prefix="/auth", tags=["auth"])

# TODO: POST /auth/signup  -- hash password (argon2), create User
# TODO: POST /auth/login   -- verify password, issue JWT

class SignupRequest(BaseModel):
    username: str
    password: str

class UserPublic(BaseModel):
    id: str
    username: str
    chip_balance: int
    is_admin: bool = False

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

@router.post("/signup", response_model=UserPublic)
def signup(body: SignupRequest) -> User:
    if get_user_by_username(body.username) is not None:
        raise HTTPException(status_code=400, detail="Username already taken")
    hashed = pwd_context.hash(body.password)
    return create_user(body.username, hashed)

@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = get_user_by_username(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    token = jwt.encode(
        {"sub": user.id, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return TokenResponse(access_token=token)
