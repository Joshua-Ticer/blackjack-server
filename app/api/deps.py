"""Shared FastAPI dependencies: DB session, current-user auth, etc.

TODO:
- get_current_user(token: str = Depends(...)) -> User   (verifies JWT, loads user)
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from app.config import settings
from app.db.session import get_session
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

DatabaseSession = Annotated[AsyncSession, Depends(get_session)]

async def create_user(db: DatabaseSession, username: str, hashed_password: str) -> User:
    user = User(username=username, hashed_password=hashed_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

async def get_user_by_username(db: DatabaseSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_user_by_id(db: DatabaseSession, user_id: str) -> User | None:
    return await db.get(User, user_id)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(db: DatabaseSession, token: str = Depends(oauth2_scheme)) -> User:
    try:
        user_id = decode_access_token(token)
    except ValueError:
        raise HTTPException(401, "Could not validate credentials")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Could not validate credentials")
    return user

def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise ValueError("Could not validate credentials")

    if not isinstance(user_id, str):
        raise ValueError("Could not validate credentials")
    
    return user_id
