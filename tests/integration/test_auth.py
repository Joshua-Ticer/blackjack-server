"""Integration tests for api/routes/auth.py and api/routes/users.py via httpx.AsyncClient."""

from httpx import AsyncClient


async def test_signup_creates_user(client: AsyncClient):
    resp = await client.post(
        "/auth/signup", json={"username": "alice", "password": "s3cret!!"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["chip_balance"] == 10000
    assert body["is_admin"] is False
    assert "hashed_password" not in body


async def test_signup_duplicate_username_rejected(client: AsyncClient):
    await client.post(
        "/auth/signup", json={"username": "alice", "password": "s3cret!!"}
    )
    resp = await client.post(
        "/auth/signup", json={"username": "alice", "password": "other!!"}
    )
    assert resp.status_code == 400


async def test_login_success_returns_bearer_token(client: AsyncClient):
    await client.post(
        "/auth/signup", json={"username": "alice", "password": "s3cret!!"}
    )
    resp = await client.post(
        "/auth/login", data={"username": "alice", "password": "s3cret!!"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_wrong_password_rejected(client: AsyncClient):
    await client.post(
        "/auth/signup", json={"username": "alice", "password": "s3cret!!"}
    )
    resp = await client.post(
        "/auth/login", data={"username": "alice", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_login_unknown_user_rejected(client: AsyncClient):
    resp = await client.post(
        "/auth/login", data={"username": "nobody", "password": "x"}
    )
    assert resp.status_code == 401


async def test_get_me_requires_auth(client: AsyncClient):
    resp = await client.get("/users/me")
    assert resp.status_code == 401


async def test_get_me_returns_current_user(client: AsyncClient, signup_and_login):
    headers, user = await signup_and_login()
    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]
    assert resp.json()["username"] == user["username"]


async def test_get_me_rejects_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert resp.status_code == 401


async def test_logout_revokes_the_session(client: AsyncClient, signup_and_login):
    headers, _ = await signup_and_login()

    logout = await client.post("/auth/logout", headers=headers)
    assert logout.status_code == 200

    resp = await client.get("/users/me", headers=headers)
    assert resp.status_code == 401


async def test_logout_is_idempotent(client: AsyncClient, signup_and_login):
    headers, _ = await signup_and_login()

    first = await client.post("/auth/logout", headers=headers)
    second = await client.post("/auth/logout", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200


async def test_logging_out_one_session_does_not_revoke_a_second_login(
    client: AsyncClient, signup_and_login
):
    await signup_and_login(username="bob", password="hunter22")
    first_login = await client.post(
        "/auth/login", data={"username": "bob", "password": "hunter22"}
    )
    second_login = await client.post(
        "/auth/login", data={"username": "bob", "password": "hunter22"}
    )
    first_headers = {"Authorization": f"Bearer {first_login.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}

    await client.post("/auth/logout", headers=first_headers)

    assert (await client.get("/users/me", headers=first_headers)).status_code == 401
    assert (await client.get("/users/me", headers=second_headers)).status_code == 200
