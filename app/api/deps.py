"""Shared FastAPI dependencies: DB session, current-user auth, etc.

TODO:
- get_current_user(token: str = Depends(...)) -> User   (verifies JWT, loads user)
"""

from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from app.config import settings

# standin for phase 2
class User(BaseModel):
    id: str
    username: str
    hashed_password: str
    chip_balance: int = 10000
    is_admin: bool = False

_users_by_id: dict[str, User] = {}
_users_by_username: dict[str, User] = {}

def create_user(username: str, hashed_password: str) -> User:
    user = User(id=str(uuid4()), username=username, hashed_password=hashed_password)
    _users_by_id[user.id] = user
    _users_by_username[username] = user
    return user

def get_user_by_username(username: str) -> User | None:
    return _users_by_username.get(username)

def get_user_by_id(user_id: str) -> User | None:
    return _users_by_id.get(user_id)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        return decode_access_token(token)
    except ValueError:
        raise HTTPException(401, "Could not validate credentials")

def decode_access_token(token: str) -> User:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise ValueError("Could not validate credentials")

    if not isinstance(user_id, str):
        raise ValueError("Could not validate credentials")
    
    user = _users_by_id.get(user_id)
    if user is None:
        raise ValueError("Could not validate credentials")
    
    return user
