import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import shop.api as api
from shop.db import DEV_PASSWORD, connect, seed_database


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def fake_reply(shop_entry, _db_path, _token, message, prior=None):
    tool = "search_products" if shop_entry == "tea" else "list_services"
    return {"text": f"{shop_entry}:{message}", "tools": [tool]}


def fake_stream(shop_entry, _db_path, _token, message, prior=None):
    tool = "search_products" if shop_entry == "tea" else "list_services"
    text = f"{shop_entry}:{message}"
    yield {"type": "token", "text": text}
    yield {"type": "tool", "name": tool}
    yield {"type": "done", "text": text, "tools": [tool], "citations": []}


def test_signup_url_picks_the_shop(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    client = TestClient(api.app)
    tea = client.post("/shops/himali-tea/signup", json={
        "name": "Ada",
        "email": "ada@himali.test",
        "password": "secret-1",
        "address": "Thamel",
        "orgId": "org_b",
        "shopId": "lotus-studio",
        "role": "admin",
    })
    studio = client.post("/shops/lotus-studio/signup", json={
        "name": "Ben",
        "email": "ben@lotus.test",
        "password": "secret-2",
        "address": "Lazimpat",
        "orgId": "org_a",
        "shopId": "himali-tea",
        "role": "admin",
    })
    assert tea.status_code == 200
    assert tea.json()["orgId"] == "org_a"
    assert tea.json()["role"] == "customer"
    assert studio.status_code == 200
    assert studio.json()["orgId"] == "org_b"
    assert studio.json()["role"] == "customer"
    conn = connect(path)
    try:
        tea_row = conn.execute("SELECT org_id, role FROM users WHERE email = ?", ("ada@himali.test",)).fetchone()
        studio_row = conn.execute("SELECT org_id, role FROM users WHERE email = ?", ("ben@lotus.test",)).fetchone()
    finally:
        conn.close()
    assert tea_row["org_id"] == "org_a"
    assert tea_row["role"] == "customer"
    assert studio_row["org_id"] == "org_b"
    assert studio_row["role"] == "customer"


def test_login_gives_a_bearer_token_and_logout_blocks_chat(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    monkeypatch.setattr(api, "run_message", fake_reply)
    client = TestClient(api.app)
    logged = client.post("/login", json={
        "email": "nima@himali.test",
        "password": DEV_PASSWORD,
        "orgId": "org_b",
        "shopId": "lotus-studio",
    })
    assert logged.status_code == 200
    token = logged.json()["token"]
    assert token
    assert logged.json()["tokenType"] == "Bearer"
    assert logged.json()["orgId"] == "org_a"
    out = client.post("/logout", headers=auth_header(token))
    assert out.status_code == 200
    chat = client.post("/shops/himali-tea/chat", json={"message": "hi"}, headers=auth_header(token))
    assert chat.status_code == 401


def test_tea_token_cannot_call_the_studio(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    calls = []

    def spy(*args, **kwargs):
        calls.append(args)
        return fake_reply(*args, **kwargs)

    monkeypatch.setattr(api, "run_message", spy)
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    denied = client.post(
        "/shops/lotus-studio/chat",
        json={"message": "book a massage", "orgId": "org_b"},
        headers=auth_header(token),
    )
    assert denied.status_code == 403
    assert calls == []


def test_body_shop_id_does_not_switch_the_shop(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    seen = []

    def spy(shop_entry, db_path, token, message, prior=None):
        seen.append(shop_entry)
        return fake_reply(shop_entry, db_path, token, message)

    monkeypatch.setattr(api, "run_message", spy)
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    chat = client.post(
        "/shops/himali-tea/chat",
        json={"message": "price of jasmine", "orgId": "org_b", "shopId": "lotus-studio"},
        headers={**auth_header(token), "X-Shop-Id": "org_b", "X-Org-Id": "lotus-studio"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["text"] == "tea:price of jasmine"
    assert body["tools"] == ["search_products"]
    assert seen == ["tea"]


def test_message_21_in_the_same_minute_returns_429(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    monkeypatch.setattr(api, "clock", lambda: 1_700_000_000.0)
    monkeypatch.setattr(api, "run_message", fake_reply)
    api.hits.clear()
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    headers = auth_header(token)
    for _ in range(20):
        ok = client.post("/shops/himali-tea/chat", json={"message": "hi"}, headers=headers)
        assert ok.status_code == 200
    blocked = client.post("/shops/himali-tea/chat", json={"message": "hi"}, headers=headers)
    assert blocked.status_code == 429


def test_chat_uses_a_fake_agent_and_does_not_call_the_network(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))

    def blocked(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(api, "run_message", fake_reply)
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    chat = client.post("/shops/himali-tea/chat", json={"message": "hello"}, headers=auth_header(token))
    assert chat.status_code == 200
    assert chat.json()["tools"] == ["search_products"]


def test_tea_token_lists_only_that_users_orders(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    listed = client.get("/me/orders", headers=auth_header(token))
    assert listed.status_code == 200
    ids = [row["id"] for row in listed.json()["orders"]]
    assert "ord_nima_last" in ids
    assert "ord_sita_1" not in ids


def test_tea_token_cannot_list_studio_bookings(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    listed = client.get("/me/bookings", headers=auth_header(token))
    assert listed.status_code == 403
    assert "book_maya_past" not in listed.text


def test_user_cannot_rename_another_users_conversation(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    client = TestClient(api.app)
    nima = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    maya = client.post("/login", json={"email": "maya@lotus.test", "password": DEV_PASSWORD}).json()["token"]
    made = client.post("/conversations", json={"title": "Nima chat"}, headers=auth_header(nima))
    assert made.status_code == 200
    chat_id = made.json()["id"]
    renamed = client.patch(
        f"/conversations/{chat_id}",
        json={"title": "Stolen"},
        headers=auth_header(maya),
    )
    assert renamed.status_code == 404
    rows = client.get("/conversations", headers=auth_header(nima)).json()["conversations"]
    assert rows[0]["title"] == "Nima chat"
    hidden = client.get("/conversations", headers=auth_header(maya)).json()["conversations"]
    assert hidden == []


def test_chat_stream_saves_thread_and_reloads_after_restart(tmp_path, monkeypatch):
    path = seed_database(tmp_path / "shop.db")
    monkeypatch.setenv("SHOP_DB", str(path))
    seen_prior = []

    def spy(shop_entry, db_path, token, message, prior=None):
        seen_prior.append(list(prior or []))
        yield from fake_stream(shop_entry, db_path, token, message, prior)

    monkeypatch.setattr(api, "stream_message", spy)
    client = TestClient(api.app)
    token = client.post("/login", json={"email": "nima@himali.test", "password": DEV_PASSWORD}).json()["token"]
    made = client.post("/conversations", json={"title": "Tea thread"}, headers=auth_header(token))
    chat_id = made.json()["id"]

    with client.stream(
        "POST",
        "/shops/himali-tea/chat/stream",
        json={"message": "jasmine price", "conversationId": chat_id},
        headers=auth_header(token),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert '"type": "meta"' in body
    assert chat_id in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body

    # Fresh client = process restart for this check: history must come from Postgres.
    client2 = TestClient(api.app)
    rows = client2.get("/conversations", headers=auth_header(token)).json()["conversations"]
    thread = next(row for row in rows if row["id"] == chat_id)
    assert [msg["role"] for msg in thread["messages"]] == ["user", "assistant"]
    assert thread["messages"][0]["text"] == "jasmine price"
    assert "tea:jasmine price" in thread["messages"][1]["text"]

    with client2.stream(
        "POST",
        "/shops/himali-tea/chat/stream",
        json={"message": "and green tea?", "conversationId": chat_id},
        headers=auth_header(token),
    ) as response:
        assert response.status_code == 200
        "".join(response.iter_text())
    assert seen_prior[-1][0]["text"] == "jasmine price"
    assert seen_prior[-1][1]["text"] == "tea:jasmine price"
