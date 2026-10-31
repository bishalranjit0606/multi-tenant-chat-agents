import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncio

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from shop.agents import run_message, setup_langsmith, stream_message
from shop.auth import advance_order, login, logout, session_for, signup
from shop.db import ENTRIES, connect

MISSING_KEY = "Set GROQ_API_KEY to use the Groq chat model."
ENV_KEYS = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_CHAT_MODEL",
    "GEMINI_EMBED_MODEL",
    "LANGSMITH_API_KEY",
    "LANGSMITH_TRACING",
    "LANGSMITH_PROJECT",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_PROJECT",
)


def load_local_env():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    found = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in ENV_KEYS or name in found:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[name] = value
    for name, value in found.items():
        if os.environ.get(name, "").strip() or not value or value == "replace-me":
            continue
        os.environ[name] = value
    setup_langsmith()


load_local_env()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SLUGS = {"himali-tea": "tea", "lotus-studio": "studio"}
LIMIT = 20
WINDOW_SECONDS = 60
# Last N turns loaded into the agent for this conversationId (short-term context).
SHORT_TERM_TURNS = 12
hits = {}


def clock():
    return time.time()


def get_db():
    return os.environ.get("SHOP_DB") or None


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    email: str
    password: str
    address: str = ""


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    email: str
    password: str
    shop: str | None = None


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    message: str
    conversationId: str | None = None


class ConversationIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str = "New chat"


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str


class OrderStatusIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str


def shop_entry(slug):
    entry = SLUGS.get(slug)
    if not entry:
        raise HTTPException(status_code=404, detail="That shop is not here.")
    return entry


def bearer_token(authorization: str | None):
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def require_session(db_path, authorization):
    token = bearer_token(authorization)
    session = session_for(db_path, token) if token else None
    if not session:
        raise HTTPException(status_code=401, detail="Log in first.")
    return token, session


def too_many(db_path, user_id):
    now = clock()
    key = (str(db_path), user_id)
    recent = [stamp for stamp in hits.get(key, []) if now - stamp < WINDOW_SECONDS]
    if len(recent) >= LIMIT:
        hits[key] = recent
        return True
    recent.append(now)
    hits[key] = recent
    return False


def _citations_in(content):
    if not isinstance(content, str) or not content:
        return []
    try:
        data = json.loads(content)
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


def reply_body(result):
    if isinstance(result, dict) and "text" in result and "messages" not in result:
        return {
            "text": result["text"],
            "tools": list(result.get("tools") or []),
            "citations": list(result.get("citations") or []),
        }
    messages = result.get("messages") if isinstance(result, dict) else []
    text = ""
    tools = []
    citations = []
    for msg in messages or []:
        tool_calls = getattr(msg, "tool_calls", None) or []
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls") or tool_calls
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                tools.append(name)
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        citations.extend(_citations_in(content))
        if isinstance(content, str) and content and not tool_calls:
            text = content
    return {"text": text, "tools": tools, "citations": citations}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def conversation_for(db_path, session, conversation_id):
    conn = connect(db_path)
    try:
        return conn.execute(
            """
            SELECT id, title FROM conversations
            WHERE id = ? AND user_id = ? AND org_id = ?
            """,
            (conversation_id, session["userId"], session["orgId"]),
        ).fetchone()
    finally:
        conn.close()


def prior_messages(db_path, conversation_id):
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT role, text FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"role": row["role"], "text": row["text"]}
        for row in rows
    ][-SHORT_TERM_TURNS:]


def message_view(row):
    return {
        "role": row["role"],
        "text": row["text"],
        "tools": json.loads(row["tools_json"]),
        "citations": json.loads(row["citations_json"]),
    }


def list_conversations(db_path, session):
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, title FROM conversations
            WHERE user_id = ? AND org_id = ?
            ORDER BY created_at
            """,
            (session["userId"], session["orgId"]),
        ).fetchall()
        out = []
        for row in rows:
            messages = conn.execute(
                """
                SELECT role, text, tools_json, citations_json
                FROM messages WHERE conversation_id = ? ORDER BY id
                """,
                (row["id"],),
            ).fetchall()
            out.append({
                "id": row["id"],
                "title": row["title"],
                "messages": [message_view(item) for item in messages],
            })
        return out
    finally:
        conn.close()


def add_message(conn, conversation_id, role, text, tools, citations):
    conn.execute(
        """
        INSERT INTO messages (conversation_id, role, text, tools_json, citations_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            role,
            text,
            json.dumps(tools),
            json.dumps(citations),
            now_iso(),
        ),
    )


def login_user(db_path, email, password, shop=None):
    picked = str(shop).strip() if shop is not None else ""
    if picked:
        return login(db_path, picked, email, password)
    last = None
    for entry in ("tea", "studio"):
        result = login(db_path, entry, email, password)
        if result.get("ok"):
            return result
        last = result
    return last


@app.post("/shops/{slug}/signup")
def signup_route(slug: str, body: SignupIn, db_path: str = Depends(get_db)):
    entry = shop_entry(slug)
    result = signup(db_path, entry, body.email, body.password, body.name, body.address)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Signup failed.")
    return {
        "orgId": result["orgId"],
        "role": result["role"],
        "customerId": result["customerId"],
        "email": result["email"],
    }


@app.post("/login")
def login_route(body: LoginIn, db_path: str = Depends(get_db)):
    result = login_user(db_path, body.email, body.password, body.shop)
    if not result or not result.get("ok"):
        raise HTTPException(status_code=401, detail="Email or password is wrong.")
    return {
        "token": result["token"],
        "tokenType": "Bearer",
        "orgId": result["orgId"],
        "role": result.get("role"),
    }


@app.post("/logout")
def logout_route(
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    token, _session = require_session(db_path, authorization)
    logout(db_path, token)
    return {"ok": True}


@app.post("/shops/{slug}/orders/{order_id}/status")
def advance_order_status_route(
    slug: str,
    order_id: str,
    body: OrderStatusIn,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    entry = shop_entry(slug)
    token, session = require_session(db_path, authorization)
    if session["orgId"] != ENTRIES[entry]:
        raise HTTPException(status_code=403, detail="This login is for another shop.")
    if entry != "tea":
        raise HTTPException(status_code=404, detail="Order status advance is for the tea shop.")
    result = advance_order(db_path, token, order_id, body.status)
    if result.get("code") == "admin_only":
        raise HTTPException(status_code=403, detail=result.get("message") or "Admin only.")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Could not update that order.")
    return {"orderId": result["orderId"], "status": result["status"]}


def _prepare_chat(slug, body, db_path, authorization):
    entry = shop_entry(slug)
    token, session = require_session(db_path, authorization)
    if session["orgId"] != ENTRIES[entry]:
        raise HTTPException(status_code=403, detail="This login is for another shop.")
    if body.conversationId and not conversation_for(db_path, session, body.conversationId):
        raise HTTPException(status_code=404, detail="That chat is not yours.")
    if too_many(db_path, session["userId"]):
        raise HTTPException(status_code=429, detail="Too many messages. Wait a minute.")
    return entry, token, session


def _save_turn(db_path, conversation_id, message, reply):
    if not conversation_id:
        return
    conn = connect(db_path)
    try:
        add_message(conn, conversation_id, "user", message, [], [])
        add_message(
            conn,
            conversation_id,
            "assistant",
            reply["text"],
            reply["tools"],
            reply["citations"],
        )
        conn.commit()
    finally:
        conn.close()


def _sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/shops/{slug}/chat")
def chat_route(
    slug: str,
    body: ChatIn,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    entry, token, session = _prepare_chat(slug, body, db_path, authorization)
    prior = prior_messages(db_path, body.conversationId) if body.conversationId else []
    try:
        result = run_message(
            entry,
            db_path,
            token,
            body.message,
            prior,
            conversation_id=body.conversationId,
        )
    except RuntimeError as err:
        if str(err) != MISSING_KEY:
            raise
        raise HTTPException(status_code=503, detail=MISSING_KEY) from err
    reply = reply_body(result)
    _save_turn(db_path, body.conversationId, body.message, reply)
    return reply


@app.post("/shops/{slug}/chat/stream")
def chat_stream_route(
    slug: str,
    body: ChatIn,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    entry, token, session = _prepare_chat(slug, body, db_path, authorization)
    conversation_id = body.conversationId
    if not conversation_id:
        conversation_id = "chat_" + secrets.token_hex(6)
        title = str(body.message or "").strip()[:42] or "New chat"
        conn = connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO conversations (id, user_id, org_id, title, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, session["userId"], session["orgId"], title, now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    prior = prior_messages(db_path, conversation_id)

    async def event_gen():
        reply = {"text": "", "tools": [], "citations": []}
        yield _sse({"type": "meta", "conversationId": conversation_id, "threadId": conversation_id})
        # Let the browser paint the meta event before tools/LLM work starts.
        await asyncio.sleep(0)
        try:
            conn = connect(db_path)
            try:
                add_message(conn, conversation_id, "user", body.message, [], [])
                conn.commit()
            finally:
                conn.close()
            for event in stream_message(
                entry,
                db_path,
                token,
                body.message,
                prior,
                conversation_id=conversation_id,
            ):
                if event.get("type") == "done":
                    reply = {
                        "text": event.get("text") or "",
                        "tools": list(event.get("tools") or []),
                        "citations": list(event.get("citations") or []),
                    }
                yield _sse(event)
                await asyncio.sleep(0)
        except RuntimeError as err:
            if str(err) == MISSING_KEY:
                yield _sse({"type": "error", "detail": MISSING_KEY})
                return
            raise
        except Exception as err:
            yield _sse({"type": "error", "detail": str(err) or "Chat failed."})
            return
        conn = connect(db_path)
        try:
            add_message(
                conn,
                conversation_id,
                "assistant",
                reply["text"],
                reply["tools"],
                reply["citations"],
            )
            conn.commit()
        finally:
            conn.close()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/conversations")
def conversations_route(
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    return {"conversations": list_conversations(db_path, session)}


@app.post("/conversations")
def create_conversation_route(
    body: ConversationIn,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    title = str(body.title or "").strip() or "New chat"
    conversation_id = "chat_" + secrets.token_hex(6)
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO conversations (id, user_id, org_id, title, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, session["userId"], session["orgId"], title, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": conversation_id, "title": title, "messages": []}


@app.patch("/conversations/{conversation_id}")
def rename_conversation_route(
    conversation_id: str,
    body: RenameIn,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    if not conversation_for(db_path, session, conversation_id):
        raise HTTPException(status_code=404, detail="That chat is not yours.")
    title = str(body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Give the chat a name.")
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ? AND org_id = ?",
            (title, conversation_id, session["userId"], session["orgId"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": conversation_id, "title": title}


@app.delete("/conversations/{conversation_id}")
def delete_conversation_route(
    conversation_id: str,
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    if not conversation_for(db_path, session, conversation_id):
        raise HTTPException(status_code=404, detail="That chat is not yours.")
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ? AND org_id = ?",
            (conversation_id, session["userId"], session["orgId"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def _mine(db_path, session, shop_entry_name, sql, params):
    if session["orgId"] != ENTRIES[shop_entry_name]:
        raise HTTPException(status_code=403, detail="This login is for another shop.")
    if not session["customerId"]:
        return []
    conn = connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@app.get("/me/orders")
def my_orders_route(
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    rows = _mine(
        db_path,
        session,
        "tea",
        """
        SELECT id, status, items_json, total, created_at
        FROM orders
        WHERE org_id = ? AND customer_id = ?
        ORDER BY created_at
        """,
        (session["orgId"], session["customerId"]),
    )
    return {
        "orders": [
            {
                "id": row["id"],
                "status": row["status"],
                "total": row["total"],
                "createdAt": row["created_at"],
                "items": json.loads(row["items_json"]),
            }
            for row in rows
        ]
    }


@app.get("/me/bookings")
def my_bookings_route(
    db_path: str = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    _token, session = require_session(db_path, authorization)
    rows = _mine(
        db_path,
        session,
        "studio",
        """
        SELECT b.id, b.status, b.start, b."end", b.price, s.name AS service
        FROM bookings b
        LEFT JOIN services s ON s.id = b.service_id
        WHERE b.org_id = ? AND b.customer_id = ?
        ORDER BY b.start
        """,
        (session["orgId"], session["customerId"]),
    )
    return {
        "bookings": [
            {
                "id": row["id"],
                "status": row["status"],
                "start": row["start"],
                "end": row["end"],
                "price": row["price"],
                "service": row["service"],
            }
            for row in rows
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("shop.api:app", host="127.0.0.1", port=8000)
