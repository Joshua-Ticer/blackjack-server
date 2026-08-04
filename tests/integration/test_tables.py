"""Integration tests for api/routes/tables.py and api/routes/history.py."""

from httpx import AsyncClient

TABLE_BODY = {"name": "High Roller", "min_bet": 5, "max_bet": 500, "max_seats": 6}


async def test_list_tables_starts_empty(client: AsyncClient):
    resp = await client.get("/tables")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_table_requires_auth(client: AsyncClient):
    resp = await client.post("/tables", json=TABLE_BODY)
    assert resp.status_code == 401


async def test_create_table_requires_admin(client: AsyncClient, signup_and_login):
    headers, _ = await signup_and_login()
    resp = await client.post("/tables", json=TABLE_BODY, headers=headers)
    assert resp.status_code == 403


async def test_create_table_as_admin(client: AsyncClient, signup_and_login):
    headers, _ = await signup_and_login(admin=True)
    resp = await client.post("/tables", json=TABLE_BODY, headers=headers)
    assert resp.status_code == 200
    table = resp.json()
    assert table["name"] == "High Roller"
    assert table["status"] == "open"

    listed = await client.get("/tables")
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [table["id"]]


async def test_get_table_by_id(client: AsyncClient, signup_and_login):
    headers, _ = await signup_and_login(admin=True)
    created = await client.post("/tables", json=TABLE_BODY, headers=headers)
    table_id = created.json()["id"]

    resp = await client.get(f"/tables/{table_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == table_id


async def test_get_table_not_found(client: AsyncClient):
    resp = await client.get("/tables/does-not-exist")
    assert resp.status_code == 404


async def test_history_rounds_requires_auth(client: AsyncClient):
    resp = await client.get("/history/rounds")
    assert resp.status_code == 401


async def test_history_rounds_paginated(client: AsyncClient, signup_and_login, seed_history):
    headers, user = await signup_and_login()
    seeded = await seed_history(user["id"])

    resp = await client.get("/history/rounds", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    # newest round first
    assert [i["round_id"] for i in body["items"]] == seeded["round_ids"]

    resp2 = await client.get("/history/rounds?limit=1&offset=1", headers=headers)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["limit"] == 1
    assert body2["offset"] == 1
    assert len(body2["items"]) == 1
    assert body2["items"][0]["round_id"] == seeded["round_ids"][1]


async def test_history_ledger_requires_auth(client: AsyncClient):
    resp = await client.get("/history/ledger")
    assert resp.status_code == 401


async def test_history_ledger_paginated(client: AsyncClient, signup_and_login, seed_history):
    headers, user = await signup_and_login()
    await seed_history(user["id"])

    resp = await client.get("/history/ledger", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    # newest entry first: the seeded loss follows the win
    assert [i["type"] for i in body["items"]] == ["loss", "win"]
    assert [i["amount"] for i in body["items"]] == [-25, 25]
