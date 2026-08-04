from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(Exception):
    pass


@dataclass
class UserInfo:
    id: str
    username: str
    chip_balance: int
    is_admin: bool


@dataclass
class TableInfo:
    id: str
    name: str
    min_bet: int
    max_bet: int
    status: str


def _detail(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        first = detail[0]
        if isinstance(first, dict) and "msg" in first:
            return str(first["msg"])
    return fallback


class RestClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        self._owns_client = client is None
        self.token: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        if self.token is None:
            raise ApiError("not authenticated")
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(f"cannot reach server: {exc}") from exc

    async def signup(self, username: str, password: str) -> UserInfo:
        response = await self._request(
            "POST", "/auth/signup", json={"username": username, "password": password}
        )
        if response.status_code != 200:
            raise ApiError(_detail(response, "signup failed"))
        return _user_from(response.json())

    async def login(self, username: str, password: str) -> str:
        response = await self._request(
            "POST", "/auth/login", data={"username": username, "password": password}
        )
        if response.status_code != 200:
            raise ApiError(_detail(response, "login failed"))
        token = response.json()["access_token"]
        self.token = str(token)
        return self.token

    async def me(self) -> UserInfo:
        response = await self._request("GET", "/users/me", headers=self._auth_headers())
        if response.status_code != 200:
            raise ApiError(_detail(response, "could not load profile"))
        return _user_from(response.json())

    async def tables(self) -> list[TableInfo]:
        response = await self._request("GET", "/tables")
        if response.status_code != 200:
            raise ApiError(_detail(response, "could not load tables"))
        return [
            TableInfo(
                id=str(t["id"]),
                name=t["name"],
                min_bet=t["min_bet"],
                max_bet=t["max_bet"],
                status=t.get("status", "open"),
            )
            for t in response.json()
        ]

    def ws_url(self, table_id: str) -> str:
        scheme = "wss" if self.base_url.startswith("https") else "ws"
        host = self.base_url.split("://", 1)[-1]
        return f"{scheme}://{host}/ws/tables/{table_id}?token={self.token}"


def _user_from(payload: dict[str, Any]) -> UserInfo:
    return UserInfo(
        id=str(payload["id"]),
        username=payload["username"],
        chip_balance=int(payload["chip_balance"]),
        is_admin=bool(payload.get("is_admin", False)),
    )
