import json
import os
import re

from shop.auth import read_shop

TEA_TOOLS = [
    "search_knowledge",
    "search_products",
    "quote_order",
    "create_order",
    "update_order",
    "cancel_order",
    "get_order_status",
    "list_my_orders",
    "reorder",
]

STUDIO_TOOLS = [
    "search_knowledge",
    "list_services",
    "get_opening_hours",
    "find_available_slots",
    "create_booking",
    "reschedule_booking",
    "cancel_booking",
    "list_my_bookings",
]

SHOP_TOOLS = {"tea": TEA_TOOLS, "studio": STUDIO_TOOLS}

TEA_PROMPT = (
    "You are the Himali Tea House assistant. "
    "Use tools for price, stock, and orders. "
    "Cite the document and section. "
    "Wait for a yes before a write."
)

STUDIO_PROMPT = (
    "You are the Lotus Wellness Studio assistant. "
    "Times are Asia/Kathmandu. "
    "Next Tuesday afternoon means 14:00 there. "
    "Use the date and time from the tool, and do not invent one. "
    "Wait for a yes before a booking write. "
    "When the customer says yes, call create_booking once with confirm true "
    "and the same service, practitioner, and start already offered. "
    "Do not ask which service again."
)

PROMPTS = {"tea": TEA_PROMPT, "studio": STUDIO_PROMPT}

TOOL_TEXT = {
    "search_knowledge": "Search this shop's notes. Return the document and the section.",
    "search_products": "Find tea by name or category. This does not save.",
    "quote_order": "Price an order. This does not save.",
    "create_order": "Save a pending order only when confirm is true.",
    "update_order": "Change a pending order only when confirm is true.",
    "cancel_order": "Cancel a pending order only when confirm is true.",
    "get_order_status": "Read one order for this customer.",
    "list_my_orders": "List this customer's orders.",
    "reorder": "Repeat the last order at the current price and stock.",
    "list_services": "List studio services and prices.",
    "get_opening_hours": "Show opening hours and holidays in Asia/Kathmandu.",
    "find_available_slots": "Find open slots. Pass service and phrase. Next Tuesday afternoon is 14:00 in Asia/Kathmandu. This does not save.",
    "create_booking": "Save the booking only when confirm is true. Pass service, practitioner, and start from the slot already offered.",
    "reschedule_booking": "Move a booking only when confirm is true.",
    "cancel_booking": "Cancel a booking only when confirm is true.",
    "list_my_bookings": "List this customer's bookings.",
}

_DROPPED_KEYS = ("orgId", "org_id", "customerId", "customer_id", "userId", "user_id")


def call_session_tool(db_path, token, action, args=None):
    data = dict(args or {})
    for key in _DROPPED_KEYS:
        data.pop(key, None)
    return read_shop(db_path, token, action, data)


def _payload_dict(payload):
    if not payload:
        return {}
    if isinstance(payload, dict):
        data = payload
    else:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return {}
    confirm = data.get("confirm")
    if confirm is True or str(confirm).strip().lower() in {"true", "yes"}:
        data["confirm"] = True
    return data


def make_shop_tools(shop_entry, db_path, token):
    from langchain_core.tools import StructuredTool

    names = SHOP_TOOLS.get(shop_entry)
    if not names:
        raise ValueError("Pick the tea shop or the studio.")
    tools = []
    for name in names:
        tools.append(_one_tool(name, db_path, token, StructuredTool))
    return tools


def _tool_result(name, db_path, token, payload="{}", **extra):
    data = _payload_dict(payload)
    for key, value in extra.items():
        if value in ("", None):
            continue
        if key == "confirm" and value is not True:
            continue
        data[key] = value
    if data.get("confirm") is True or str(data.get("confirm")).strip().lower() in {"true", "yes"}:
        data["confirm"] = True
    if name == "search_knowledge":
        from shop.knowledge import search_for_session

        return json.dumps(search_for_session(db_path, token, data))
    return json.dumps(call_session_tool(db_path, token, name, data))


def _one_tool(name, db_path, token, structured_tool):
    if name in {"create_booking", "reschedule_booking", "cancel_booking"}:
        def _run(
            service: str = "",
            phrase: str = "",
            start: str = "",
            practitioner: str = "",
            confirm: bool = False,
            payload: str = "{}",
        ) -> str:
            return _tool_result(
                name,
                db_path,
                token,
                payload,
                service=service,
                phrase=phrase,
                start=start,
                practitioner=practitioner,
                confirm=confirm,
            )
    elif name == "find_available_slots":
        def _run(
            service: str = "",
            phrase: str = "",
            practitioner: str = "",
            payload: str = "{}",
        ) -> str:
            return _tool_result(
                name,
                db_path,
                token,
                payload,
                service=service,
                phrase=phrase,
                practitioner=practitioner,
            )
    else:
        def _run(payload: str = "{}", query: str = "") -> str:
            return _tool_result(name, db_path, token, payload, query=query)

    _run.__name__ = name
    return structured_tool.from_function(
        func=_run,
        name=name,
        description=TOOL_TEXT[name],
    )


def setup_langsmith():
    """Turn on LangSmith when LANGSMITH_API_KEY (or LANGCHAIN_API_KEY) is set."""
    key = (
        os.environ.get("LANGSMITH_API_KEY", "").strip()
        or os.environ.get("LANGCHAIN_API_KEY", "").strip()
    )
    if not key or key == "replace-me":
        return False
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ.setdefault("LANGCHAIN_API_KEY", key)
    tracing = (
        os.environ.get("LANGSMITH_TRACING")
        or os.environ.get("LANGCHAIN_TRACING_V2")
        or "true"
    ).strip().lower()
    if tracing in {"1", "true", "yes", "on"}:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
    else:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return False
    project = (
        os.environ.get("LANGSMITH_PROJECT", "").strip()
        or os.environ.get("LANGCHAIN_PROJECT", "").strip()
        or "multi-tenant-chat-agents"
    )
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project
    return True


def run_config(shop_entry, conversation_id=None):
    setup_langsmith()
    meta = {"shop": shop_entry}
    if conversation_id:
        meta["conversation_id"] = conversation_id
        meta["thread_id"] = conversation_id
    return {
        "run_name": f"{shop_entry}-chat",
        "tags": [f"shop:{shop_entry}", "himali-lotus"],
        "metadata": meta,
    }


def build_model():
    from shop.knowledge import groq_key

    key = groq_key()
    if not key:
        raise RuntimeError("Set GROQ_API_KEY to use the Groq chat model.")
    from langchain_openai import ChatOpenAI

    model_name = os.environ.get("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
    return ChatOpenAI(
        model=model_name,
        api_key=key,
        base_url="https://api.groq.com/openai/v1",
        streaming=True,
    )


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""


def _history_messages(prior, message):
    messages = []
    for item in prior or []:
        role = item.get("role") if isinstance(item, dict) else None
        text = item.get("text") if isinstance(item, dict) else None
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": message})
    return messages


def _citations_in(content):
    text = _content_text(content)
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(matches, list):
        return []
    found = []
    for match in matches:
        if isinstance(match, dict) and match.get("document") and match.get("section"):
            found.append({"document": match["document"], "section": match["section"]})
    return found


def build_agent(shop_entry, db_path, token):
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        build_model(),
        make_shop_tools(shop_entry, db_path, token),
        prompt=PROMPTS[shop_entry],
    )


def _plain_yes(text):
    words = re.findall(r"[a-z]+", (text or "").lower())
    return words in (
        ["yes"],
        ["y"],
        ["yeah"],
        ["yep"],
        ["ok"],
        ["okay"],
        ["confirm"],
        ["book", "it"],
        ["just", "book", "it"],
    )


def _offered_service(prior, services):
    blob = "\n".join(
        item.get("text") or ""
        for item in prior or []
        if isinstance(item, dict)
    ).lower()
    found = []
    for service in services:
        name = str(service.get("name") or "")
        if name and name.lower() in blob:
            found.append((blob.rfind(name.lower()), name))
    if not found:
        return ""
    found.sort()
    return found[-1][1]


def confirm_yes(db_path, token, message, prior):
    if not _plain_yes(message):
        return None
    last = ""
    for item in prior or []:
        if isinstance(item, dict) and item.get("role") == "assistant" and item.get("text"):
            last = item["text"]
    if not re.search(r"\d{1,2}:\d{2}", last):
        return None
    listed = call_session_tool(db_path, token, "list_services", {})
    service = _offered_service(prior, listed.get("services") or [])
    if not service or service.lower() not in last.lower():
        return None
    slots = call_session_tool(db_path, token, "find_available_slots", {
        "service": service,
        "phrase": "next Tuesday afternoon",
    })
    choices = slots.get("slots") or []
    slot = None
    for choice in choices:
        if str(choice.get("local") or "").endswith("14:00"):
            slot = choice
            break
    if slot is None and choices:
        slot = choices[0]
    if not slot:
        return None
    booked = call_session_tool(db_path, token, "create_booking", {
        "service": slot.get("serviceName") or service,
        "practitioner": slot.get("practitionerName"),
        "start": slot.get("start"),
        "confirm": True,
    })
    if not booked.get("ok"):
        return {
            "text": booked.get("message") or "That slot could not be booked.",
            "tools": ["create_booking"],
            "citations": [],
        }
    summary = booked.get("summary") or {}
    return {
        "text": (
            f"Booked {summary.get('service')} with {summary.get('practitioner')} "
            f"on {summary.get('date')} at {summary.get('time')} Asia/Kathmandu. "
            f"Price NPR {summary.get('price')}."
        ),
        "tools": ["create_booking"],
        "citations": [],
    }


def run_message(shop_entry, db_path, token, message, prior=None, conversation_id=None):
    if shop_entry == "studio":
        booked = confirm_yes(db_path, token, message, prior)
        if booked:
            return booked
    agent = build_agent(shop_entry, db_path, token)
    return agent.invoke(
        {"messages": _history_messages(prior, message)},
        config=run_config(shop_entry, conversation_id),
    )


def stream_message(shop_entry, db_path, token, message, prior=None, conversation_id=None):
    """Yield SSE-ready events while the agent runs.

    Short-term memory is `prior` (recent turns for this conversationId).
    Long-term memory stays in Postgres messages for that thread.
    """
    if shop_entry == "studio":
        booked = confirm_yes(db_path, token, message, prior)
        if booked:
            text = booked.get("text") or ""
            if text:
                yield {"type": "token", "text": text}
            for name in booked.get("tools") or []:
                yield {"type": "tool", "name": name}
            yield {
                "type": "done",
                "text": text,
                "tools": list(booked.get("tools") or []),
                "citations": list(booked.get("citations") or []),
            }
            return

    from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

    agent = build_agent(shop_entry, db_path, token)
    tools = []
    citations = []
    text_parts = []
    for chunk, _metadata in agent.stream(
        {"messages": _history_messages(prior, message)},
        config=run_config(shop_entry, conversation_id),
        stream_mode="messages",
    ):
        if isinstance(chunk, ToolMessage):
            for cite in _citations_in(getattr(chunk, "content", None)):
                if cite not in citations:
                    citations.append(cite)
                    yield {"type": "citation", **cite}
            continue
        if not isinstance(chunk, (AIMessageChunk, AIMessage)):
            continue
        for call in getattr(chunk, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name and name not in tools:
                tools.append(name)
                yield {"type": "tool", "name": name}
        piece = _content_text(getattr(chunk, "content", None))
        if piece:
            # AIMessage (non-chunk) can repeat full text; keep deltas only for chunks.
            if isinstance(chunk, AIMessage) and not isinstance(chunk, AIMessageChunk):
                if "".join(text_parts) == piece:
                    continue
                if text_parts and piece.startswith("".join(text_parts)):
                    piece = piece[len("".join(text_parts)):]
                if not piece:
                    continue
            text_parts.append(piece)
            yield {"type": "token", "text": piece}
    yield {
        "type": "done",
        "text": "".join(text_parts),
        "tools": tools,
        "citations": citations,
    }
