"""Signup / login / token issuance."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

# TODO: POST /auth/signup  -- hash password (argon2), create User
# TODO: POST /auth/login   -- verify password, issue JWT
