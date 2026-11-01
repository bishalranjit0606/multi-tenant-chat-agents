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
    token = login(path, "tea", "bishal@tea.com", DEV_PASSWORD)["token"]
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
    token = login(path, "tea", "bishal@tea.com", DEV_PASSWORD)["token"]
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


def _studio_tools(path, token, pending, confirm_ok):
    return {
        tool.name: tool
        for tool in make_shop_tools("studio", path, token, pending=pending, confirm_ok=confirm_ok)
    }


def test_yes_books_the_slot_that_was_shown_not_14_00(tmp_path):
    import shop.agents as agents

    path = seed_database(tmp_path / "shop.db")
    token = login(path, "studio", "bishal@studio.com", DEV_PASSWORD)["token"]
    pending = []
    tools = _studio_tools(path, token, pending, confirm_ok=False)
    preview = json.loads(tools["create_booking"].invoke({
        "service": "Swedish massage",
        "practitioner": "Anita",
        "phrase": "next tuesday 4:30 pm",
        "confirm": True,
    }))
    assert preview["code"] == "confirm_required"
    assert preview["summary"]["time"] == "16:30"
    key = agents._pending_key(token, "chat_1")
    agents._remember_pending(key, pending)
    done = agents.confirm_pending(path, token, "yes", "chat_1")
    assert "16:30" in done["text"]
    assert done["tools"] == ["create_booking"]
    listed = call_session_tool(path, token, "list_my_bookings", {})
    assert [row["startLocal"][-5:] for row in listed["upcoming"]] == ["16:30"]
    assert listed["upcoming"][0]["practitioner"] == "Anita"
    assert agents.confirm_pending(path, token, "yes", "chat_1") is None


def test_changing_the_service_reschedules_instead_of_booking_again(tmp_path):
    import shop.agents as agents

    path = seed_database(tmp_path / "shop.db")
    token = login(path, "studio", "bishal@studio.com", DEV_PASSWORD)["token"]
    booked = call_session_tool(path, token, "create_booking", {
        "service": "Swedish massage",
        "practitioner": "Anita",
        "phrase": "next tuesday 2 pm",
        "confirm": True,
    })
    booking_id = booked["booking"]["id"]
    pending = []
    tools = _studio_tools(path, token, pending, confirm_ok=False)
    preview = json.loads(tools["reschedule_booking"].invoke({
        "booking_id": booking_id,
        "service": "Deep tissue massage",
    }))
    assert preview["code"] == "confirm_required"
    agents._remember_pending(agents._pending_key(token, "chat_2"), pending)
    done = agents.confirm_pending(path, token, "ok", "chat_2")
    assert "Deep tissue" in done["text"]
    listed = call_session_tool(path, token, "list_my_bookings", {})
    assert len(listed["upcoming"]) == 1
    assert listed["upcoming"][0]["id"] == booking_id
    assert listed["upcoming"][0]["service"] == "Deep tissue massage"


def test_cancel_takes_a_booking_id_and_cancels_all_after_one_yes(tmp_path):
    import shop.agents as agents

    path = seed_database(tmp_path / "shop.db")
    token = login(path, "studio", "bishal@studio.com", DEV_PASSWORD)["token"]
    ids = []
    for phrase in ("next tuesday 2 pm", "next wednesday 3 pm"):
        made = call_session_tool(path, token, "create_booking", {
            "service": "Swedish massage",
            "practitioner": "Anita",
            "phrase": phrase,
            "confirm": True,
        })
        ids.append(made["booking"]["id"])
    pending = []
    tools = _studio_tools(path, token, pending, confirm_ok=False)
    for booking_id in ids:
        preview = json.loads(tools["cancel_booking"].invoke({"booking_id": booking_id}))
        assert preview["code"] == "confirm_required"
    past = json.loads(tools["cancel_booking"].invoke({"booking_id": "book_maya_past"}))
    assert past["code"] == "past_booking"
    agents._remember_pending(agents._pending_key(token, "chat_3"), pending)
    done = agents.confirm_pending(path, token, "yes cancel all", "chat_3")
    assert done["text"].count("Cancelled booking") == 2
    listed = call_session_tool(path, token, "list_my_bookings", {})
    assert listed["upcoming"] == []


def test_studio_prompt_has_todays_date(monkeypatch):
    import shop.agents as agents

    seen = {}

    def fake_create(model, tools, **kwargs):
        seen["prompt"] = kwargs.get("prompt")
        return "graph"

    monkeypatch.setattr(agents, "build_model", lambda: "fake-model")
    import langgraph.prebuilt as prebuilt

    monkeypatch.setattr(prebuilt, "create_react_agent", fake_create)
    agents.build_agent("studio", "unused.db", "token")
    assert "Today is " in seen["prompt"]
    assert "Never show UTC" in seen["prompt"]


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
