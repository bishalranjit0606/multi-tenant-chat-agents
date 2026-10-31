import json
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shop.agents import make_shop_tools
from shop.auth import login
from shop.db import DEV_PASSWORD, database_url
from shop.knowledge import chunk_count, rebuild, search_notes
from shop.seed import seed

STUDIO_POLICY = "A later cancel keeps 50 percent of the price."


def test_database_url_points_at_postgres():
    url = database_url()
    assert url.startswith("postgres")


def test_tea_storage_cites_faq_storage(tmp_path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    path = rebuild(tmp_path / "shop")
    matches = search_notes("org_a", "How do I store the tea?", path)
    assert matches[0]["document"] == "FAQ"
    assert matches[0]["section"] == "Storage"


def test_tea_search_does_not_return_studio_policy(tmp_path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    path = rebuild(tmp_path / "shop")
    matches = search_notes("org_a", "studio cancellation policy hours fee", path)
    blob = json.dumps(matches)
    assert STUDIO_POLICY not in blob
    assert "Lotus Wellness" not in blob
    assert all(row["document"] != "Policies" for row in matches)


def test_studio_search_can_return_cancellation(tmp_path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    path = rebuild(tmp_path / "shop")
    matches = search_notes("org_b", "cancellation fee hours", path)
    assert any(row["document"] == "Policies" and row["section"] == "Cancellation" for row in matches)


def test_knowledge_tool_uses_the_session_shop(tmp_path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    path = rebuild(tmp_path / "shop")
    token = login(path, "tea", "bishal@tea.com", DEV_PASSWORD)["token"]
    tool = next(item for item in make_shop_tools("tea", path, token) if item.name == "search_knowledge")
    result = json.loads(tool.invoke({
        "payload": json.dumps({
            "query": "How do I store the tea?",
            "orgId": "org_b",
            "org_id": "org_b",
        }),
    }))
    assert result["matches"][0]["document"] == "FAQ"
    assert result["matches"][0]["section"] == "Storage"
    assert STUDIO_POLICY not in json.dumps(result)


def test_rebuild_uses_a_fake_embedder_and_does_not_call_mistral(tmp_path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls = []
    real_create = socket.create_connection
    real_connect = socket.socket.connect

    def local_host(address):
        host = address[0] if isinstance(address, tuple) else ""
        return host in ("127.0.0.1", "localhost", "::1")

    def guard_create(address, *args, **kwargs):
        if local_host(address):
            return real_create(address, *args, **kwargs)
        raise AssertionError("network")

    def guard_connect(self, address, *args, **kwargs):
        if local_host(address):
            return real_connect(self, address, *args, **kwargs)
        raise AssertionError("network")

    def no_mistral(texts):
        calls.append(texts)
        raise AssertionError("mistral")

    monkeypatch.setattr(socket, "create_connection", guard_create)
    monkeypatch.setattr(socket.socket, "connect", guard_connect)
    import shop.knowledge as knowledge

    monkeypatch.setattr(knowledge, "gemini_embed", no_mistral)
    path = rebuild(tmp_path / "shop")
    assert chunk_count(path) == len(seed["knowledge"])
    matches = search_notes("org_a", "How do I store the tea?", path)
    assert matches[0]["section"] == "Storage"
    assert calls == []
    assert "MISTRAL" not in os.environ.get("MISTRAL_API_KEY", "")
