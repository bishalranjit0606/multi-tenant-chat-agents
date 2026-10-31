import importlib
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shop.agents import (
    STUDIO_TOOLS,
    TEA_TOOLS,
    call_session_tool,
    make_shop_tools,
)
from shop.auth import login
from shop.db import DEV_PASSWORD, seed_database


def test_tea_tools_have_orders_and_not_create_booking():
    names = [tool.name for tool in make_shop_tools("tea", "unused.db", "token")]
    assert names == TEA_TOOLS
    assert "create_order" in names
    assert "create_booking" not in names
    assert "reschedule_booking" not in names
    assert "cancel_booking" not in names


def test_studio_tools_have_bookings_and_not_create_order():
    names = [tool.name for tool in make_shop_tools("studio", "unused.db", "token")]
    assert names == STUDIO_TOOLS
    assert "create_booking" in names
    assert "create_order" not in names
    assert "update_order" not in names
    assert "cancel_order" not in names
    assert "reorder" not in names


def test_langgraph_gets_each_shops_tools(monkeypatch):
    import shop.agents as agents

    seen = {}

    def fake_create(model, tools, **kwargs):
        seen["model"] = model
        seen["names"] = [tool.name for tool in tools]
        seen["prompt"] = kwargs.get("prompt")
        return "graph"

    monkeypatch.setattr(agents, "build_model", lambda: "fake-model")
    import langgraph.prebuilt as prebuilt

    monkeypatch.setattr(prebuilt, "create_react_agent", fake_create)
    assert agents.build_agent("tea", "unused.db", "token") == "graph"
    assert seen["model"] == "fake-model"
    assert "create_order" in seen["names"]
    assert "create_booking" not in seen["names"]
    assert "price, stock, and orders" in seen["prompt"]
    assert "document and section" in seen["prompt"]
    assert "yes" in seen["prompt"]

    assert agents.build_agent("studio", "unused.db", "token") == "graph"
    assert "create_booking" in seen["names"]
    assert "create_order" not in seen["names"]
    assert "Asia/Kathmandu" in seen["prompt"]
    assert "14:00" in seen["prompt"]
    assert "yes" in seen["prompt"]


def test_tea_token_list_bookings_gets_no_studio_rows(tmp_path):
    path = seed_database(tmp_path / "shop.db")
    token = login(path, "tea", "nima@himali.test", DEV_PASSWORD)["token"]
    result = call_session_tool(path, token, "list_my_bookings", {
        "orgId": "org_b",
        "org_id": "org_b",
        "customerId": "b_maya",
    })
    blob = json.dumps(result)
    assert "book_maya_past" not in blob
    assert "book_arun_past" not in blob


def test_tool_org_id_does_not_switch_the_session(tmp_path):
    path = seed_database(tmp_path / "shop.db")
    token = login(path, "tea", "nima@himali.test", DEV_PASSWORD)["token"]
    result = call_session_tool(path, token, "search_products", {
        "orgId": "org_b",
        "org_id": "org_b",
        "query": "",
    })
    assert any(row["sku"] == "TEA-JAS-50" for row in result["products"])
    tool = next(tool for tool in make_shop_tools("tea", path, token) if tool.name == "search_products")
    raw = tool.invoke({"payload": json.dumps({"orgId": "org_b", "query": ""})})
    assert "TEA-JAS-50" in raw
    assert "svc_swedish" not in raw


def test_importing_the_agent_module_does_not_call_the_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    sys.modules.pop("shop.agents", None)
    import shop.agents as agents

    importlib.reload(agents)
    assert "create_booking" not in agents.TEA_TOOLS
    assert "create_order" not in agents.STUDIO_TOOLS
