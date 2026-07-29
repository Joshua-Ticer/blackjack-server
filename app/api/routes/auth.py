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
