"""Read-only admin stats. Every query is scoped with WHERE org_id = ?.

Each public function takes (db_path, org_id, period) and only runs SELECT.
"""

import json
from datetime import date, datetime, timedelta, timezone

from shop.db import connect
from shop.rules import (
    TIME_ZONE,
    WEEKDAYS,
    as_utc,
    kathmandu_parts,
    kathmandu_to_utc,
    local_text,
    to_iso,
)

PERIODS = ("today", "this_week", "last_7_days", "all")
LOW_STOCK = 5
MAX_ROWS = 20

PERIOD_TEXT = {
    "today": "today, from 00:00 to 24:00 Asia/Kathmandu",
    "this_week": "this week, Sunday 00:00 to next Sunday 00:00 Asia/Kathmandu",
    "last_7_days": "the last 7 days, from now minus 7 days to now",
    "all": "all time",
}


def clean_period(period):
    text = str(period or "today").strip().lower().replace(" ", "_").replace("-", "_")
    if text not in PERIODS:
        raise ValueError(f"period must be one of: {', '.join(PERIODS)}.")
    return text


def resolve_window(period, now=None):
    period = clean_period(period)
    moment = as_utc(now) if now is not None else datetime.now(timezone.utc)
    parts = kathmandu_parts(moment)
    midnight = kathmandu_to_utc(parts["year"], parts["month"], parts["day"], 0, 0)
    if period == "today":
        start, end = midnight, midnight + timedelta(days=1)
    elif period == "this_week":
        start = midnight - timedelta(days=WEEKDAYS.index(parts["weekday"]))
        end = start + timedelta(days=7)
    elif period == "last_7_days":
        start, end = moment - timedelta(days=7), moment
    else:
        start, end = None, None
    return {"period": period, "start": start, "end": end}


def window_view(win):
    return {
        "period": win["period"],
        "timeZone": TIME_ZONE,
        "start": local_text(win["start"]) if win["start"] else None,
        "end": local_text(win["end"]) if win["end"] else None,
        "text": PERIOD_TEXT[win["period"]],
    }


def _window_sql(column, win):
    if win["start"] is None:
        return "", ()
    return f" AND {column} >= ? AND {column} < ?", (to_iso(win["start"]), to_iso(win["end"]))


def _rows(db_path, sql, params):
    conn = connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _result(org_id, win, definition, **data):
    return {"ok": True, "orgId": org_id, "window": window_view(win), "definition": definition, **data}


def _limit(limit):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 5
    return max(1, min(value, MAX_ROWS))


def _chatters(db_path, org_id, win):
    clause, params = _window_sql("c.created_at", win)
    return _rows(
        db_path,
        f"""
        SELECT c.id, c.user_id, c.created_at, u.customer_id
        FROM conversations c
        JOIN users u ON u.id = c.user_id AND u.org_id = c.org_id
        WHERE c.org_id = ? AND u.role = 'customer'{clause}
        """,
        (org_id, *params),
    )


# ---------- shared ----------

def client_stats(db_path, org_id, period, now=None):
    win = resolve_window(period, now)
    rows = _chatters(db_path, org_id, win)
    return _result(
        org_id,
        win,
        "Unique customers who chatted = distinct customer user ids with a conversation created in the window. "
        "New sign-ups are not tracked: users have no sign-up date.",
        uniqueCustomersChatted=len({row["user_id"] for row in rows}),
        conversations=len(rows),
        newSignups="not tracked",
    )


# ---------- tea ----------

def order_stats(db_path, org_id, period, now=None):
    win = resolve_window(period, now)
    clause, params = _window_sql("created_at", win)
    rows = _rows(
        db_path,
        f"""
        SELECT id, status, total, created_at FROM orders
        WHERE org_id = ?{clause}
        ORDER BY created_at DESC
        """,
        (org_id, *params),
    )
    by_status = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    kept = [row for row in rows if row["status"] != "cancelled"]
    revenue = sum(row["total"] for row in kept)
    return _result(
        org_id,
        win,
        "Orders created in the window (created_at). Revenue = sum of total in NPR, cancelled orders left out. "
        "Average order value = revenue / orders that are not cancelled.",
        orderCount=len(rows),
        byStatus=by_status,
        revenue=revenue,
        avgOrderValue=round(revenue / len(kept), 2) if kept else 0,
        currency="NPR",
        orders=[
            {"id": row["id"], "status": row["status"], "total": row["total"], "createdLocal": local_text(row["created_at"])}
            for row in rows[:MAX_ROWS]
        ],
    )


def top_products(db_path, org_id, period, limit=5, now=None):
    win = resolve_window(period, now)
    clause, params = _window_sql("created_at", win)
    orders = _rows(
        db_path,
        f"SELECT items_json FROM orders WHERE org_id = ? AND status <> 'cancelled'{clause}",
        (org_id, *params),
    )
    products = _rows(
        db_path,
        "SELECT sku, name, stock FROM products WHERE org_id = ? ORDER BY stock, sku",
        (org_id,),
    )
    names = {row["sku"]: row["name"] for row in products}
    sold = {}
    for order in orders:
        for item in json.loads(order["items_json"]):
            sku = item.get("sku")
            if sku not in names:
                continue
            line = sold.setdefault(sku, {"sku": sku, "name": names[sku], "qty": 0, "revenue": 0})
            line["qty"] += int(item.get("qty") or 0)
            line["revenue"] += int(item.get("lineTotal") or 0)
    ranked = sorted(sold.values(), key=lambda row: (-row["qty"], row["sku"]))
    return _result(
        org_id,
        win,
        "Best sellers = quantity summed from order items in the window, cancelled orders left out. "
        f"Low stock = stock of {LOW_STOCK} or less right now (stock is not windowed).",
        topProducts=ranked[:_limit(limit)],
        lowStock=[{"sku": row["sku"], "name": row["name"], "stock": row["stock"]} for row in products if row["stock"] <= LOW_STOCK],
    )


def tea_conversion(db_path, org_id, period, now=None):
    win = resolve_window(period, now)
    chats = _chatters(db_path, org_id, win)
    clause, params = _window_sql("created_at", win)
    buyers = {
        row["customer_id"]
        for row in _rows(
            db_path,
            f"SELECT DISTINCT customer_id FROM orders WHERE org_id = ?{clause}",
            (org_id, *params),
        )
    }
    converted = sum(1 for row in chats if row["customer_id"] in buyers)
    return _result(
        org_id,
        win,
        "Conversion = conversations created in the window whose customer placed an order (any status) "
        "in the same window, divided by all customer conversations in the window.",
        conversations=len(chats),
        converted=converted,
        rate=round(converted / len(chats), 4) if chats else 0,
    )


# ---------- studio ----------

def _bookings(db_path, org_id, win):
    clause, params = _window_sql("b.start", win)
    return _rows(
        db_path,
        f"""
        SELECT b.id, b.status, b.start, b."end", b.customer_id, b.practitioner_id, b.service_id,
               s.name AS service, p.name AS practitioner
        FROM bookings b
        LEFT JOIN services s ON s.id = b.service_id AND s.org_id = b.org_id
        LEFT JOIN practitioners p ON p.id = b.practitioner_id AND p.org_id = b.org_id
        WHERE b.org_id = ?{clause}
        ORDER BY b.start
        """,
        (org_id, *params),
    )


def _overlap_minutes(start, end, lo, hi):
    left, right = max(start, lo), min(end, hi)
    return max(0, (right - left).total_seconds() / 60)


def _open_minutes(db_path, org_id, lo, hi):
    hours = {
        row["weekday"]: (row["open"], row["close"])
        for row in _rows(db_path, "SELECT weekday, open, close FROM hours WHERE org_id = ?", (org_id,))
    }
    holidays = {row["date"] for row in _rows(db_path, "SELECT date FROM holidays WHERE org_id = ?", (org_id,))}
    first = kathmandu_parts(lo)
    last = kathmandu_parts(hi)
    day = date(first["year"], first["month"], first["day"])
    stop = date(last["year"], last["month"], last["day"])
    total = 0
    while day <= stop:
        key = day.isoformat()
        span = hours.get(WEEKDAYS[(day.weekday() + 1) % 7])
        if span and key not in holidays:
            oh, om = (int(x) for x in span[0].split(":"))
            ch, cm = (int(x) for x in span[1].split(":"))
            opens = kathmandu_to_utc(day.year, day.month, day.day, oh, om)
            closes = kathmandu_to_utc(day.year, day.month, day.day, ch, cm)
            total += _overlap_minutes(opens, closes, lo, hi)
        day += timedelta(days=1)
    return total


def booking_stats(db_path, org_id, period, now=None):
    win = resolve_window(period, now)
    rows = _bookings(db_path, org_id, win)
    by_status = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    kept = [row for row in rows if row["status"] != "cancelled"]
    lo, hi = win["start"], win["end"]
    if lo is None and kept:
        lo = min(as_utc(row["start"]) for row in kept)
        hi = max(as_utc(row["end"]) for row in kept)
    practitioners = _rows(
        db_path,
        "SELECT id, name FROM practitioners WHERE org_id = ? ORDER BY id",
        (org_id,),
    )
    open_each = _open_minutes(db_path, org_id, lo, hi) if lo is not None else 0
    utilisation = []
    for person in practitioners:
        booked = sum(
            _overlap_minutes(as_utc(row["start"]), as_utc(row["end"]), lo, hi)
            for row in kept
            if row["practitioner_id"] == person["id"]
        ) if lo is not None else 0
        utilisation.append({
            "practitioner": person["name"],
            "bookedMinutes": round(booked),
            "openMinutes": round(open_each),
            "rate": round(booked / open_each, 4) if open_each else 0,
        })
    booked_all = sum(row["bookedMinutes"] for row in utilisation)
    open_all = sum(row["openMinutes"] for row in utilisation)
    return _result(
        org_id,
        win,
        "Bookings whose start is in the window. Cancellations = status cancelled. "
        "Utilisation = booked minutes (not cancelled) / open minutes from opening hours, holidays closed. "
        "For all time, utilisation spans the first to the last booking.",
        bookingCount=len(rows),
        byStatus=by_status,
        cancellations=by_status.get("cancelled", 0),
        utilisation={
            "overall": round(booked_all / open_all, 4) if open_all else 0,
            "byPractitioner": utilisation,
        },
        bookings=[
            {
                "id": row["id"],
                "status": row["status"],
                "service": row["service"],
                "practitioner": row["practitioner"],
                "startLocal": local_text(row["start"]),
            }
            for row in rows[:MAX_ROWS]
        ],
    )


def top_services(db_path, org_id, period, limit=5, now=None):
    win = resolve_window(period, now)
    kept = [row for row in _bookings(db_path, org_id, win) if row["status"] != "cancelled"]
    services = {}
    hours = {}
    for row in kept:
        name = row["service"] or row["service_id"]
        services[name] = services.get(name, 0) + 1
        hour = kathmandu_parts(row["start"])["hour"]
        hours[hour] = hours.get(hour, 0) + 1
    size = _limit(limit)
    return _result(
        org_id,
        win,
        "Most-booked services = bookings (not cancelled) whose start is in the window, grouped by service. "
        "Busiest hours = the same bookings grouped by start hour in Asia/Kathmandu.",
        topServices=[
            {"service": name, "bookings": count}
            for name, count in sorted(services.items(), key=lambda item: (-item[1], item[0]))[:size]
        ],
        busiestHours=[
            {"hour": f"{hour:02d}:00-{(hour + 1) % 24:02d}:00", "bookings": count}
            for hour, count in sorted(hours.items(), key=lambda item: (-item[1], item[0]))[:size]
        ],
    )


def studio_conversion(db_path, org_id, period, now=None):
    win = resolve_window(period, now)
    chats = _chatters(db_path, org_id, win)
    rows = _rows(
        db_path,
        "SELECT customer_id, start FROM bookings WHERE org_id = ? AND status <> 'cancelled'",
        (org_id,),
    )
    starts = {}
    for row in rows:
        starts.setdefault(row["customer_id"], []).append(as_utc(row["start"]))
    converted = 0
    for chat in chats:
        opened = as_utc(chat["created_at"])
        if any(start >= opened for start in starts.get(chat["customer_id"], [])):
            converted += 1
    return _result(
        org_id,
        win,
        "Conversion = conversations created in the window whose customer has a booking (not cancelled) "
        "starting at or after the chat, divided by all customer conversations in the window. "
        "Bookings have no created time, so this is an estimate.",
        conversations=len(chats),
        converted=converted,
        rate=round(converted / len(chats), 4) if chats else 0,
    )
