import json
import os
import re
import tempfile

# Eval uses the fake tool planner, not a live chat model or paid embedder.
os.environ["MISTRAL_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

from shop.agents import SHOP_TOOLS
from shop.auth import login, session_for
from shop.db import DEV_PASSWORD, connect, load_store
from shop.knowledge import rebuild, search_for_session
from shop.rules import run_tool

from eval.scenarios import ARUN_START, TAKEN_START, all_cases

NOW = "2026-10-30T06:15:00.000Z"
LATE_START = "2026-11-03T14:15:00.000Z"
JASMINE_LINE = [{"sku": "TEA-JAS-50", "qty": 1}]


def plan(shop, message):
    text = message.lower()
    if shop == "tea":
        if "ignore your rules" in text:
            return [
                ("list_my_bookings", {"orgId": "org_b", "customerId": "b_maya"}),
                ("search_knowledge", {"query": "studio cancellation policy hours fee", "orgId": "org_b"}),
            ]
        if "studio bookings" in text:
            return [("list_my_bookings", {"orgId": "org_b", "customerId": "b_maya"})]
        if "store the tea" in text:
            return [("search_knowledge", {"query": message})]
        if "wifi" in text:
            return [("search_knowledge", {"query": message})]
        if "quote" in text:
            return [("quote_order", {"items": JASMINE_LINE})]
        if "100 jasmine" in text:
            return [("create_order", {"items": [{"sku": "TEA-JAS-50", "qty": 100}], "confirm": True})]
        if "confirm false" in text:
            return [("create_order", {"items": JASMINE_LINE, "confirm": False})]
        if "one jasmine" in text:
            return [("create_order", {"items": JASMINE_LINE, "confirm": True})]
        if "cancel order" in text:
            order_id = re.search(r"ord_[a-z0-9_]+", message).group(0)
            return [("cancel_order", {"orderId": order_id, "confirm": True})]
        if "ord_sita_1" in text:
            return [("get_order_status", {"orderId": "ord_sita_1", "orgId": "org_b"})]
        if "same as last time" in text:
            return [("reorder", {"confirm": True})]
        return []
    if "ignore your rules" in text:
        return [
            ("list_my_orders", {"orgId": "org_a"}),
            ("search_knowledge", {"query": "jasmine tea order ord_sita_1", "orgId": "org_a"}),
        ]
    if "tea orders" in text:
        return [("list_my_orders", {"orgId": "org_a"})]
    if "cancellation fee" in text:
        return [("search_knowledge", {"query": "cancellation fee hours"})]
    if "wifi" in text:
        return [("search_knowledge", {"query": message})]
    if "list the services" in text:
        return [("list_services", {})]
    if text.startswith("find a slot"):
        return [("find_available_slots", {
            "phrase": "next Tuesday afternoon",
            "serviceId": "svc_swedish",
            "now": NOW,
        })]
    if "confirm false" in text:
        return [("create_booking", {
            "phrase": "next Tuesday afternoon",
            "serviceId": "svc_swedish",
            "practitionerId": "p_anita",
            "now": NOW,
            "confirm": False,
        })]
    if "move my booking" in text:
        return [("reschedule_booking", {
            "bookingId": "book_eval_maya",
            "start": ARUN_START,
            "confirm": True,
        })]
    if "taken slot" in text:
        return [("create_booking", {
            "serviceId": "svc_swedish",
            "practitionerId": "p_anita",
            "start": TAKEN_START,
            "confirm": True,
        })]
    if "20:00" in text:
        return [("create_booking", {
            "serviceId": "svc_swedish",
            "practitionerId": "p_anita",
            "start": LATE_START,
            "confirm": True,
        })]
    if "book swedish" in text:
        return [("create_booking", {
            "phrase": "next Tuesday afternoon",
            "serviceId": "svc_swedish",
            "practitionerId": "p_anita",
            "now": NOW,
            "confirm": True,
        })]
    if "book_arun_past" in text:
        return [("list_my_bookings", {"orgId": "org_a", "customerId": "b_arun"})]
    return []


def snapshot(path):
    conn = connect(path)
    try:
        orders = [
            (
                row["id"],
                row["status"],
                row["customer_id"],
                json.dumps(json.loads(row["items_json"]), sort_keys=True),
            )
            for row in conn.execute("SELECT id, status, customer_id, items_json FROM orders ORDER BY id")
        ]
        bookings = [
            (row["id"], row["status"], row["customer_id"], row["start"])
            for row in conn.execute('SELECT id, status, customer_id, start FROM bookings ORDER BY id')
        ]
    finally:
        conn.close()
    return {"orders": orders, "bookings": bookings}


def save_store(path, store):
    conn = connect(path)
    try:
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM bookings")
        conn.execute("DELETE FROM products")
        for row in store["products"]:
            conn.execute(
                "INSERT INTO products (sku, org_id, name, category, price, stock) VALUES (?, ?, ?, ?, ?, ?)",
                (row["sku"], row["orgId"], row["name"], row["category"], row["price"], row["stock"]),
            )
        for row in store["orders"]:
            conn.execute(
                """
                INSERT INTO orders (
                    id, org_id, customer_id, status, items_json, total, address, payment,
                    stock_held, history_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["orgId"],
                    row["customerId"],
                    row["status"],
                    json.dumps(row["items"]),
                    row["total"],
                    row["address"],
                    row["payment"],
                    bool(row["stockHeld"]),
                    json.dumps(row["history"]),
                    row["createdAt"],
                ),
            )
        for row in store["bookings"]:
            conn.execute(
                """
                INSERT INTO bookings (
                    id, org_id, customer_id, service_id, practitioner_id, start, "end", price, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["orgId"],
                    row["customerId"],
                    row["serviceId"],
                    row["practitionerId"],
                    row["start"],
                    row["end"],
                    row["price"],
                    row["status"],
                ),
            )
        conn.execute("UPDATE meta SET value = ? WHERE key = 'seq'", (str(store["seq"]),))
        conn.commit()
    finally:
        conn.close()


def run_allowed_tool(shop, path, token, name, args):
    if name not in SHOP_TOOLS[shop]:
        return {"ok": False, "code": "not_on_this_agent"}
    if name == "search_knowledge":
        return search_for_session(path, token, args)
    session = session_for(path, token)
    store = load_store(path)
    result = run_tool(store, name, {
        "sessionOrgId": session["orgId"],
        "sessionCustomerId": session["customerId"],
        "args": args,
    })
    save_store(path, store)
    return result


def reply_for(shop, path, token, message):
    results = [run_allowed_tool(shop, path, token, name, args) for name, args in plan(shop, message)]
    return json.dumps(results)


def run_case(case, folder):
    path = rebuild(os.path.join(folder, case["shop"], re.sub(r"[^a-z0-9]+", "-", case["name"].lower())[:40]))
    prepare = case.get("prepare")
    if prepare:
        prepare(path)
    logged = login(path, case["shop"], case["email"], DEV_PASSWORD)
    if not logged.get("ok"):
        return "login failed"
    before = snapshot(path)
    reply = reply_for(case["shop"], path, logged["token"], case["message"])
    after = snapshot(path)
    reasons = []
    for check in case["checks"]:
        reason = check(reply, before, after)
        if reason:
            reasons.append(reason)
    return "; ".join(reasons)


def main():
    url = os.environ.get("DATABASE_URL", "")
    if ":5433" not in url:
        print("fail setup: DATABASE_URL must use port 5433")
        return 1
    cases = all_cases()
    tea = [case for case in cases if case["shop"] == "tea"]
    studio = [case for case in cases if case["shop"] == "studio"]
    if len(tea) < 12 or len(studio) < 12:
        print("fail setup: need 12 tea cases and 12 studio cases")
        return 1
    passed = 0
    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        for case in cases:
            reason = run_case(case, folder)
            if reason:
                failed += 1
                print(f"fail {case['name']} {reason}")
            else:
                passed += 1
                print(f"pass {case['name']}")
    print(f"{passed} pass, {failed} fail")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
