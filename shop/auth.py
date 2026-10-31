import secrets

import bcrypt

from shop.db import (
    ENTRIES,
    connect,
    delete_session,
    get_session,
    get_user_by_email,
    insert_customer,
    insert_session,
    insert_user,
    load_store,
    save_shop_writes,
)
from shop.rules import advance_order_status, fail, run_tool


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def password_ok(password, password_hash):
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def signup(db_path, shop_entry, email, password, name, address, org_id=None, role=None, customer_id=None):
    del org_id, role, customer_id
    org = ENTRIES.get(shop_entry)
    if not org:
        return fail("unknown_shop", "Pick the tea shop or the studio.")
    clean_email = str(email or "").strip().lower()
    if not clean_email or not password or not str(name or "").strip():
        return fail("bad_signup", "Name, email, and password are required.")
    conn = connect(db_path)
    try:
        if get_user_by_email(conn, org, clean_email):
            return fail("email_taken", "That email is already used at this shop.")
        new_customer_id = "c_" + secrets.token_hex(4)
        user_id = "user_" + secrets.token_hex(4)
        insert_customer(conn, {
            "id": new_customer_id,
            "orgId": org,
            "name": str(name).strip(),
            "address": address or "",
        })
        insert_user(conn, {
            "id": user_id,
            "org_id": org,
            "customer_id": new_customer_id,
            "email": clean_email,
            "password_hash": hash_password(password),
            "role": "customer",
        })
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "orgId": org, "role": "customer", "customerId": new_customer_id, "email": clean_email}


def login(db_path, shop_entry, email, password):
    org = ENTRIES.get(shop_entry)
    if not org:
        return fail("unknown_shop", "Pick the tea shop or the studio.")
    clean_email = str(email or "").strip().lower()
    conn = connect(db_path)
    try:
        user = get_user_by_email(conn, org, clean_email)
        if not user or not password_ok(password, user["password_hash"]):
            return fail("bad_login", "Email or password is wrong.")
        token = secrets.token_urlsafe(32)
        role = user["role"]
        insert_session(conn, {
            "token": token,
            "user_id": user["id"],
            "org_id": user["org_id"],
            "customer_id": user["customer_id"],
            "role": role,
        })
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "token": token, "orgId": org, "role": role}


def logout(db_path, token):
    conn = connect(db_path)
    try:
        delete_session(conn, token)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def session_for(db_path, token):
    if not token:
        return None
    conn = connect(db_path)
    try:
        row = get_session(conn, token)
        if not row:
            return None
        return {
            "userId": row["user_id"],
            "orgId": row["org_id"],
            "customerId": row["customer_id"],
            "role": row["role"],
        }
    finally:
        conn.close()


WRITES = {
    "create_order",
    "update_order",
    "cancel_order",
    "reorder",
    "create_booking",
    "reschedule_booking",
    "cancel_booking",
    "advance_order_status",
}


def read_shop(db_path, token, action, args=None):
    session = session_for(db_path, token)
    if not session:
        return fail("logged_out", "Log in first.")
    store = load_store(db_path)
    result = run_tool(store, action, {
        "sessionOrgId": session["orgId"],
        "sessionCustomerId": session["customerId"],
        "args": args or {},
    })
    if action in WRITES and isinstance(result, dict) and result.get("ok"):
        save_shop_writes(db_path, store)
    return result


def advance_order(db_path, token, order_id, status):
    session = session_for(db_path, token)
    if not session:
        return fail("logged_out", "Log in first.")
    if session.get("role") != "admin":
        return fail("admin_only", "Only a shop admin can advance order status.")
    store = load_store(db_path)
    result = advance_order_status(store, {
        "orgId": session["orgId"],
        "orderId": order_id,
        "status": status,
    })
    if isinstance(result, dict) and result.get("ok"):
        save_shop_writes(db_path, store)
    return result
