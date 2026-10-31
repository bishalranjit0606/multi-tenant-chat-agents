import copy
import math
import re
from datetime import datetime, timedelta, timezone

TIME_ZONE = "Asia/Kathmandu"
OFFSET = timedelta(hours=5, minutes=45)
KTM = timezone(OFFSET)
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
STOP_WORDS = {
    "the", "and", "for", "how", "you", "your", "what", "with",
    "this", "that", "are", "can", "does", "from", "about",
}


def create_store(source):
    store = copy.deepcopy(source)
    store["seq"] = 100
    return store


def _seq_ok(seq):
    if type(seq) not in (int, float):
        return False
    if isinstance(seq, float) and math.isnan(seq):
        return False
    return True


def choose_state(candidates, source):
    ready = [row for row in (candidates or []) if row and row.get("store")]
    ready.sort(key=lambda row: row.get("savedAt") or 0, reverse=True)
    best = ready[0] if ready else None
    store = best["store"] if best else create_store(source)
    sessions = best.get("sessions") if best and best.get("sessions") else {}
    if not _seq_ok(store.get("seq")):
        store["seq"] = 100
    saved_at = best.get("savedAt") if best and best.get("savedAt") else 0
    return {"store": store, "sessions": sessions, "savedAt": saved_at}


def as_utc(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_iso(value):
    moment = as_utc(value)
    millis = moment.microsecond // 1000
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def epoch_ms(value):
    return round(as_utc(value).timestamp() * 1000)


def kathmandu_parts(value):
    local = as_utc(value).astimezone(KTM)
    weekday = WEEKDAYS[(local.weekday() + 1) % 7]
    return {
        "year": local.year,
        "month": local.month,
        "day": local.day,
        "weekday": weekday,
        "hour": local.hour,
        "minute": local.minute,
        "dateKey": f"{local.year:04d}-{local.month:02d}-{local.day:02d}",
    }


def kathmandu_to_utc(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc) - OFFSET


def resolve_phrase(phrase, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    text = str(phrase or "").lower()
    if "tuesday" not in text or "afternoon" not in text:
        return fail("unparsed_phrase", "Say a clearer time, such as next Tuesday afternoon.")
    start = kathmandu_parts(now)
    today = WEEKDAYS.index(start["weekday"])
    delta = (2 - today + 7) % 7
    if delta == 0:
        delta = 7
    today_afternoon = kathmandu_to_utc(start["year"], start["month"], start["day"], 14, 0)
    target = today_afternoon + timedelta(days=delta)
    parts = kathmandu_parts(target)
    return {
        "ok": True,
        "timeZone": TIME_ZONE,
        "start": to_iso(target),
        "local": parts["dateKey"] + " 14:00",
        "weekday": parts["weekday"],
        "hour": parts["hour"],
    }


def next_id(store, prefix):
    if not _seq_ok(store.get("seq")):
        store["seq"] = 100
    store["seq"] = int(store["seq"]) + 1
    return prefix + str(store["seq"])


def customer_row(store, org_id, customer_id):
    for row in store["customers"]:
        if row["id"] == customer_id and row["orgId"] == org_id:
            return row
    return None


def fail(code, message, extra=None):
    out = {"ok": False, "code": code, "message": message}
    if extra:
        out.update(extra)
    return out


def require_customer(store, org_id, customer_id):
    customer = customer_row(store, org_id, customer_id)
    if not customer:
        return fail("wrong_org", "This customer is not in this shop.")
    return {"ok": True, "customer": customer}


def product_row(store, org_id, sku):
    for row in store["products"]:
        if row["orgId"] == org_id and row["sku"] == sku:
            return row
    return None


def whole_number(qty):
    if isinstance(qty, bool):
        return False
    if isinstance(qty, int):
        return True
    if isinstance(qty, float):
        return qty.is_integer()
    return False


def merge_lines(items):
    if not isinstance(items, list) or len(items) == 0:
        return fail("items_required", "Add at least one product.")
    merged = {}
    for row in items:
        row = row or {}
        sku = str(row.get("sku") or "").strip()
        qty = row.get("qty")
        if not sku or not whole_number(qty) or int(qty) < 1:
            return fail("bad_item", "Each item needs a sku and a whole quantity of 1 or more.")
        merged[sku] = merged.get(sku, 0) + int(qty)
    return {"ok": True, "lines": [{"sku": sku, "qty": qty} for sku, qty in merged.items()]}


def alternative_for(store, org_id, product, need):
    options = [
        row for row in store["products"]
        if row["orgId"] == org_id
        and row["category"] == product["category"]
        and row["sku"] != product["sku"]
        and row["stock"] >= need
    ]
    options.sort(key=lambda row: (-row["stock"], row["sku"]))
    if not options:
        return None
    pick = options[0]
    return {
        "sku": pick["sku"],
        "name": pick["name"],
        "price": pick["price"],
        "stock": pick["stock"],
        "category": pick["category"],
    }


def held_qty(lines, sku):
    return sum(row["qty"] for row in (lines or []) if row["sku"] == sku)


def price_lines(store, org_id, lines, held_lines):
    priced = []
    problems = []
    for line in lines:
        item = product_row(store, org_id, line["sku"])
        if not item:
            problems.append({
                "sku": line["sku"],
                "code": "unknown_sku",
                "message": "That product is not in this shop.",
            })
            continue
        have = item["stock"] + held_qty(held_lines, line["sku"])
        if line["qty"] > have:
            alternative = alternative_for(store, org_id, item, line["qty"])
            if alternative:
                message = f"Only {have} left of {item['name']}. You can try {alternative['name']} instead."
            else:
                message = f"Only {have} left of {item['name']}."
            problems.append({
                "sku": line["sku"],
                "name": item["name"],
                "code": "insufficient_stock",
                "have": have,
                "need": line["qty"],
                "alternative": alternative,
                "message": message,
            })
        priced.append({
            "sku": item["sku"],
            "name": item["name"],
            "qty": line["qty"],
            "unitPrice": item["price"],
            "lineTotal": item["price"] * line["qty"],
        })
    total = sum(row["lineTotal"] for row in priced)
    return {"priced": priced, "problems": problems, "total": total}


def summary_of(priced, address):
    return {
        "items": priced["priced"],
        "total": priced["total"],
        "payment": "cash_on_delivery",
        "address": address or "",
    }


def reserve(store, org_id, lines):
    for line in lines:
        product_row(store, org_id, line["sku"])["stock"] -= line["qty"]


def release(store, org_id, lines):
    for line in lines:
        item = product_row(store, org_id, line["sku"])
        if item:
            item["stock"] += line["qty"]


def own_order(store, org_id, customer_id, order_id):
    order = next((row for row in store["orders"] if row["id"] == order_id), None)
    if not order:
        return fail("not_your_order", "That order is not in this shop.")
    if order["orgId"] != org_id or order["customerId"] != customer_id:
        return fail("not_your_order", "That order is not yours.")
    return {"ok": True, "order": order}


def pending_only(order, verb):
    if order["status"] == "pending":
        return {"ok": True}
    return fail(
        "not_pending",
        f"This order is {order['status']}. Only a pending order can be {verb}.",
        {"status": order["status"]},
    )


def word_stem(word):
    if len(word) > 5 and word.endswith("age"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("e"):
        return word[:-1]
    return word


def search_knowledge(store, data):
    org_id = data.get("orgId")
    words = [
        word_stem(word)
        for word in re.split(r"[^a-z0-9]+", str(data.get("query") or "").lower())
        if len(word) > 2 and word not in STOP_WORDS
    ]
    scored = []
    for row in store["knowledge"]:
        if row["orgId"] != org_id:
            continue
        section = (row["document"] + " " + row["section"]).lower()
        text = row["text"].lower()
        score = 0
        for word in words:
            if word in section:
                score += 5
            elif word in text:
                score += 1
        if score > 0:
            scored.append({"row": row, "score": score})
    scored.sort(key=lambda hit: hit["score"], reverse=True)
    return {
        "ok": True,
        "matches": [
            {"document": hit["row"]["document"], "section": hit["row"]["section"], "text": hit["row"]["text"]}
            for hit in scored[:3]
        ],
    }


def search_products(store, data):
    name = str(data.get("name") or data.get("query") or "").lower()
    category = str(data.get("category") or "").lower()
    min_price = None if data.get("minPrice") is None else float(data.get("minPrice"))
    max_price = None if data.get("maxPrice") is None else float(data.get("maxPrice"))
    rows = []
    for row in store["products"]:
        if row["orgId"] != data.get("orgId"):
            continue
        if name and name not in row["name"].lower() and name not in row["sku"].lower():
            continue
        if category and row["category"] != category:
            continue
        if min_price is not None and not math.isnan(min_price) and row["price"] < min_price:
            continue
        if max_price is not None and not math.isnan(max_price) and row["price"] > max_price:
            continue
        rows.append(row)
    return {
        "ok": True,
        "products": [
            {
                "sku": row["sku"],
                "name": row["name"],
                "category": row["category"],
                "price": row["price"],
                "stock": row["stock"],
            }
            for row in rows
        ],
    }


def quote_order(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    norm = merge_lines(data.get("items"))
    if not norm["ok"]:
        return norm
    priced = price_lines(store, data["orgId"], norm["lines"], [])
    summary = summary_of(priced, data.get("address") or gate["customer"]["address"])
    if priced["problems"]:
        return fail(
            "insufficient_stock",
            priced["problems"][0]["message"],
            {"problems": priced["problems"], "summary": summary},
        )
    return {"ok": True, "summary": summary, "message": "This is a quote. Nothing is saved yet."}


def create_order(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    norm = merge_lines(data.get("items"))
    if not norm["ok"]:
        return norm
    priced = price_lines(store, data["orgId"], norm["lines"], [])
    address = data.get("address") or gate["customer"]["address"]
    summary = summary_of(priced, address)
    if priced["problems"]:
        return fail(
            "insufficient_stock",
            priced["problems"][0]["message"],
            {"problems": priced["problems"], "summary": summary},
        )
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Show this summary and wait for a yes. Then call create_order with confirm true.",
            {"summary": summary},
        )
    again = price_lines(store, data["orgId"], norm["lines"], [])
    if again["problems"]:
        return fail(
            "insufficient_stock",
            again["problems"][0]["message"],
            {"problems": again["problems"], "summary": summary_of(again, address)},
        )
    reserve(store, data["orgId"], norm["lines"])
    at = to_iso(datetime.now(timezone.utc))
    order = {
        "id": next_id(store, "ord_"),
        "orgId": data["orgId"],
        "customerId": data["customerId"],
        "status": "pending",
        "items": again["priced"],
        "total": again["total"],
        "address": address,
        "payment": "cash_on_delivery",
        "stockHeld": True,
        "history": [{"status": "pending", "at": at}],
        "createdAt": at,
    }
    store["orders"].append(order)
    return {"ok": True, "order": order, "summary": summary}


def update_order(store, data):
    owned = own_order(store, data.get("orgId"), data.get("customerId"), data.get("orderId"))
    if not owned["ok"]:
        return owned
    order = owned["order"]
    pending = pending_only(order, "changed")
    if not pending["ok"]:
        return pending
    held = order["items"] if order.get("stockHeld") else []
    if data.get("items"):
        norm = merge_lines(data.get("items"))
    else:
        norm = {"ok": True, "lines": [{"sku": row["sku"], "qty": row["qty"]} for row in order["items"]]}
    if not norm["ok"]:
        return norm
    priced = price_lines(store, data["orgId"], norm["lines"], held)
    address = data.get("address") or order["address"]
    summary = summary_of(priced, address)
    if priced["problems"]:
        return fail(
            "insufficient_stock",
            priced["problems"][0]["message"],
            {"problems": priced["problems"], "summary": summary, "status": order["status"]},
        )
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Show this summary and wait for a yes. Then call update_order with confirm true.",
            {"summary": summary, "status": order["status"]},
        )
    if order.get("stockHeld"):
        release(store, data["orgId"], order["items"])
    reserve(store, data["orgId"], norm["lines"])
    order["items"] = priced["priced"]
    order["total"] = priced["total"]
    order["address"] = address
    order["stockHeld"] = True
    order["history"].append({"status": "pending", "at": to_iso(datetime.now(timezone.utc)), "note": "updated"})
    return {"ok": True, "order": order, "summary": summary}


def cancel_order(store, data):
    owned = own_order(store, data.get("orgId"), data.get("customerId"), data.get("orderId"))
    if not owned["ok"]:
        return owned
    order = owned["order"]
    pending = pending_only(order, "cancelled")
    if not pending["ok"]:
        return pending
    summary = {
        "orderId": order["id"],
        "status": order["status"],
        "items": order["items"],
        "total": order["total"],
    }
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Wait for a yes before cancelling this pending order.",
            {"summary": summary, "status": order["status"]},
        )
    if order.get("stockHeld"):
        release(store, data["orgId"], order["items"])
    order["stockHeld"] = False
    order["status"] = "cancelled"
    order["history"].append({"status": "cancelled", "at": to_iso(datetime.now(timezone.utc))})
    return {"ok": True, "order": order, "summary": summary}


def get_order_status(store, data):
    owned = own_order(store, data.get("orgId"), data.get("customerId"), data.get("orderId"))
    if not owned["ok"]:
        return owned
    order = owned["order"]
    return {
        "ok": True,
        "orderId": order["id"],
        "status": order["status"],
        "items": order["items"],
        "total": order["total"],
        "history": order["history"],
        "address": order["address"],
        "payment": order["payment"],
    }


def list_my_orders(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    rows = [
        row for row in store["orders"]
        if row["orgId"] == data.get("orgId") and row["customerId"] == data.get("customerId")
    ]
    rows.sort(key=lambda row: str(row["createdAt"]), reverse=True)
    return {
        "ok": True,
        "orders": [
            {
                "id": row["id"],
                "status": row["status"],
                "items": row["items"],
                "total": row["total"],
                "createdAt": row["createdAt"],
            }
            for row in rows
        ],
    }


def reorder(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    mine = [
        row for row in store["orders"]
        if row["orgId"] == data.get("orgId")
        and row["customerId"] == data.get("customerId")
        and row["status"] != "cancelled"
    ]
    mine.sort(key=lambda row: str(row["createdAt"]), reverse=True)
    if not mine:
        return fail("no_previous_order", "There is no earlier order to repeat.")
    last = mine[0]
    lines = [{"sku": row["sku"], "qty": row["qty"]} for row in last["items"]]
    notes = []
    for line in last["items"]:
        item = product_row(store, data["orgId"], line["sku"])
        if not item:
            continue
        if item["price"] != line["unitPrice"]:
            notes.append({"sku": line["sku"], "type": "price", "from": line["unitPrice"], "to": item["price"]})
        if item["stock"] < line["qty"]:
            notes.append({"sku": line["sku"], "type": "stock", "need": line["qty"], "have": item["stock"]})
    priced = price_lines(store, data["orgId"], lines, [])
    summary = summary_of(priced, last["address"])
    summary["fromOrderId"] = last["id"]
    summary["notes"] = notes
    if priced["problems"]:
        return fail(
            "insufficient_stock",
            priced["problems"][0]["message"],
            {"notes": notes, "problems": priced["problems"], "summary": summary},
        )
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Show the last order with current prices and wait for a yes.",
            {"notes": notes, "summary": summary},
        )
    created = create_order(store, {
        "orgId": data["orgId"],
        "customerId": data["customerId"],
        "items": lines,
        "address": last["address"],
        "confirm": True,
    })
    created["notes"] = notes
    if not created["ok"]:
        return created
    created["fromOrderId"] = last["id"]
    return created


def advance_order_status(store, data):
    order = next(
        (row for row in store["orders"] if row["id"] == data.get("orderId") and row["orgId"] == data.get("orgId")),
        None,
    )
    if not order:
        return fail("not_your_order", "That order is not in this shop.")
    allowed = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
    if data.get("status") not in allowed:
        return fail("bad_status", "That status is not used.")
    order["status"] = data["status"]
    order["history"].append({"status": data["status"], "at": to_iso(datetime.now(timezone.utc)), "note": "staff"})
    return {"ok": True, "orderId": order["id"], "status": order["status"]}


def named_row(rows, org_id, key):
    name = str(key or "").strip().lower()
    mine = [row for row in rows if row["orgId"] == org_id]
    for row in mine:
        if row["id"] == key:
            return row
    for row in mine:
        if row["name"].lower() == name:
            return row
    if name:
        for row in mine:
            if name in row["name"].lower():
                return row
    return None


def service_row(store, org_id, service_id):
    return named_row(store["services"], org_id, service_id)


def practitioner_row(store, org_id, practitioner_id):
    return named_row(store["practitioners"], org_id, practitioner_id)


def minutes_of(hhmm):
    bits = str(hhmm).split(":")
    return int(bits[0]) * 60 + int(bits[1])


def slot_fits(store, org_id, start, end):
    open_at = kathmandu_parts(start)
    close_at = kathmandu_parts(end)
    if open_at["dateKey"] != close_at["dateKey"]:
        return fail("too_short", "That slot is not long enough for this service.")
    holiday = next(
        (row for row in store["holidays"] if row["orgId"] == org_id and row["date"] == open_at["dateKey"]),
        None,
    )
    if holiday:
        return fail("holiday", "The studio is closed that day.", {"holiday": holiday["name"]})
    hours = next(
        (row for row in store["hours"] if row["orgId"] == org_id and row["weekday"] == open_at["weekday"]),
        None,
    )
    if not hours:
        return fail("outside_hours", "That time is outside opening hours.")
    open_min = minutes_of(hours["open"])
    close_min = minutes_of(hours["close"])
    start_min = open_at["hour"] * 60 + open_at["minute"]
    end_min = close_at["hour"] * 60 + close_at["minute"]
    if start_min < open_min or start_min >= close_min:
        return fail("outside_hours", "That time is outside opening hours.")
    if end_min > close_min:
        return fail("too_short", "That slot is not long enough for this service.")
    return {"ok": True, "dateKey": open_at["dateKey"]}


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def conflicts(store, data):
    ignore = data.get("ignoreBookingId")
    rows = [
        row for row in store["bookings"]
        if row["status"] == "booked" and row["id"] != ignore and row["orgId"] == data["orgId"]
    ]
    practitioner_busy = False
    customer_busy = False
    for row in rows:
        if not overlaps(data["startMs"], data["endMs"], epoch_ms(row["start"]), epoch_ms(row["end"])):
            continue
        if row["practitionerId"] == data["practitionerId"]:
            practitioner_busy = True
        if row["customerId"] == data["customerId"]:
            customer_busy = True
    return {"practitionerBusy": practitioner_busy, "customerBusy": customer_busy}


def each_date_key(from_key, to_key):
    from_bits = [int(part) for part in from_key.split("-")]
    to_bits = [int(part) for part in to_key.split("-")]
    cursor = epoch_ms(kathmandu_to_utc(from_bits[0], from_bits[1], from_bits[2], 12, 0))
    end = epoch_ms(kathmandu_to_utc(to_bits[0], to_bits[1], to_bits[2], 12, 0))
    keys = []
    while cursor <= end and len(keys) < 31:
        keys.append(kathmandu_parts(datetime.fromtimestamp(cursor / 1000, timezone.utc))["dateKey"])
        cursor += 24 * 60 * 60 * 1000
    return keys


def list_services(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    return {
        "ok": True,
        "services": [
            {"id": row["id"], "name": row["name"], "durationMin": row["durationMin"], "price": row["price"]}
            for row in store["services"]
            if row["orgId"] == data.get("orgId")
        ],
    }


def get_opening_hours(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    return {
        "ok": True,
        "timeZone": TIME_ZONE,
        "hours": [
            {"weekday": row["weekday"], "open": row["open"], "close": row["close"]}
            for row in store["hours"]
            if row["orgId"] == data.get("orgId")
        ],
        "holidays": [
            {"date": row["date"], "name": row["name"]}
            for row in store["holidays"]
            if row["orgId"] == data.get("orgId")
        ],
    }


def find_available_slots(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    service = service_row(store, data.get("orgId"), data.get("serviceId") or data.get("serviceName") or data.get("service"))
    if not service:
        return fail("unknown_service", "That service is not at this studio.")
    practitioner_key = data.get("practitionerId") or data.get("practitionerName") or data.get("practitioner")
    people = [row for row in store["practitioners"] if row["orgId"] == data.get("orgId")]
    if practitioner_key:
        person = practitioner_row(store, data.get("orgId"), practitioner_key)
        if not person:
            return fail("unknown_practitioner", "That practitioner is not at this studio.")
        people = [person]
    from_key = data.get("from")
    to_key = data.get("to")
    min_hour = None
    max_hour = None
    now_value = as_utc(data["now"]) if data.get("now") is not None else datetime.now(timezone.utc)
    if data.get("phrase"):
        when = resolve_phrase(data["phrase"], now_value)
        if not when["ok"]:
            return when
        from_key = when["local"][:10]
        to_key = from_key
        if "afternoon" in str(data["phrase"]).lower():
            min_hour = 14
            max_hour = 17
    today = kathmandu_parts(now_value)["dateKey"]
    if not from_key:
        from_key = today
    if not to_key:
        to_key = from_key
    slots = []
    for date_key in each_date_key(from_key, to_key):
        bits = [int(part) for part in date_key.split("-")]
        noon = kathmandu_parts(kathmandu_to_utc(bits[0], bits[1], bits[2], 12, 0))
        hours = next(
            (row for row in store["hours"] if row["orgId"] == data.get("orgId") and row["weekday"] == noon["weekday"]),
            None,
        )
        if not hours:
            continue
        if any(row["orgId"] == data.get("orgId") and row["date"] == date_key for row in store["holidays"]):
            continue
        open_min = minutes_of(hours["open"])
        close_min = minutes_of(hours["close"])
        minute = open_min
        while minute + service["durationMin"] <= close_min:
            start = kathmandu_to_utc(bits[0], bits[1], bits[2], minute // 60, minute % 60)
            end = start + timedelta(minutes=service["durationMin"])
            for person in people:
                hit = conflicts(store, {
                    "orgId": data.get("orgId"),
                    "practitionerId": person["id"],
                    "customerId": data.get("customerId"),
                    "startMs": epoch_ms(start),
                    "endMs": epoch_ms(end),
                })
                if hit["practitionerBusy"] or hit["customerBusy"]:
                    continue
                local = kathmandu_parts(start)
                if min_hour is not None and (local["hour"] < min_hour or local["hour"] >= max_hour):
                    continue
                slots.append({
                    "start": to_iso(start),
                    "end": to_iso(end),
                    "local": f"{local['dateKey']} {local['hour']:02d}:{local['minute']:02d}",
                    "serviceId": service["id"],
                    "serviceName": service["name"],
                    "durationMin": service["durationMin"],
                    "price": service["price"],
                    "practitionerId": person["id"],
                    "practitionerName": person["name"],
                })
                break
            minute += 30
    return {"ok": True, "timeZone": TIME_ZONE, "slots": slots}


def booking_summary(service, person, start, price):
    local = kathmandu_parts(start)
    return {
        "serviceId": service["id"],
        "service": service["name"],
        "practitionerId": person["id"],
        "practitioner": person["name"],
        "date": local["dateKey"],
        "time": f"{local['hour']:02d}:{local['minute']:02d}",
        "timeZone": TIME_ZONE,
        "price": price,
    }


def lock_booking(store, data):
    hit = conflicts(store, data)
    if hit["practitionerBusy"]:
        return fail("slot_taken", "That time was just taken. Pick another slot.")
    if hit["customerBusy"]:
        return fail("customer_busy", "You already have a booking at that time.")
    return {"ok": True}


def nearest_slots(store, data, start):
    from_key = kathmandu_parts(start)["dateKey"]
    to_key = kathmandu_parts(start + timedelta(days=7))["dateKey"]
    found = find_available_slots(store, {
        "orgId": data.get("orgId"),
        "customerId": data.get("customerId"),
        "serviceId": data.get("serviceId"),
        "practitionerId": data.get("practitionerId"),
        "from": from_key,
        "to": to_key,
    })
    if not found["ok"]:
        return []
    start_iso = to_iso(start)
    return [slot for slot in found["slots"] if slot["start"] != start_iso][:3]


def _parse_start(start_value):
    if not start_value:
        return None
    try:
        return as_utc(start_value)
    except ValueError:
        return None


def create_booking(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    service = service_row(store, data.get("orgId"), data.get("serviceId") or data.get("serviceName") or data.get("service"))
    if not service:
        return fail("unknown_service", "That service is not at this studio.")
    person = practitioner_row(
        store,
        data.get("orgId"),
        data.get("practitionerId") or data.get("practitionerName") or data.get("practitioner"),
    )
    if not person:
        return fail("unknown_practitioner", "That practitioner is not at this studio.")
    start_value = data.get("start")
    if not start_value and data.get("phrase"):
        when = resolve_phrase(data["phrase"], as_utc(data["now"]) if data.get("now") is not None else datetime.now(timezone.utc))
        if not when["ok"]:
            return when
        start_value = when["start"]
    start = _parse_start(start_value)
    if start is None:
        return fail("bad_time", "Give a start time.")
    end = start + timedelta(minutes=service["durationMin"])
    fit = slot_fits(store, data.get("orgId"), start, end)
    if not fit["ok"]:
        return fit
    summary = booking_summary(service, person, start, service["price"])
    lock = lock_booking(store, {
        "orgId": data.get("orgId"),
        "practitionerId": person["id"],
        "customerId": data.get("customerId"),
        "startMs": epoch_ms(start),
        "endMs": epoch_ms(end),
    })
    if not lock["ok"]:
        lock["summary"] = summary
        lock["nearest"] = nearest_slots(store, data, start)
        return lock
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Show the service, practitioner, date, time, and price. Wait for a yes.",
            {"summary": summary},
        )
    again = lock_booking(store, {
        "orgId": data.get("orgId"),
        "practitionerId": person["id"],
        "customerId": data.get("customerId"),
        "startMs": epoch_ms(start),
        "endMs": epoch_ms(end),
    })
    if not again["ok"]:
        again["summary"] = summary
        again["nearest"] = nearest_slots(store, data, start)
        return again
    booking = {
        "id": next_id(store, "book_"),
        "orgId": data.get("orgId"),
        "customerId": data.get("customerId"),
        "serviceId": service["id"],
        "practitionerId": person["id"],
        "start": to_iso(start),
        "end": to_iso(end),
        "price": service["price"],
        "status": "booked",
    }
    store["bookings"].append(booking)
    return {"ok": True, "booking": booking, "summary": summary}


def reschedule_booking(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    booking = next((row for row in store["bookings"] if row["id"] == data.get("bookingId")), None)
    if (
        not booking
        or booking["orgId"] != data.get("orgId")
        or booking["customerId"] != data.get("customerId")
        or booking["status"] != "booked"
    ):
        return fail("not_your_booking", "That booking is not yours.")
    service = service_row(store, data.get("orgId"), booking["serviceId"])
    practitioner_id = data.get("practitionerId") or booking["practitionerId"]
    person = practitioner_row(store, data.get("orgId"), practitioner_id)
    if not service or not person:
        return fail("unknown_practitioner", "That practitioner is not at this studio.")
    start = _parse_start(data.get("start"))
    if start is None:
        return fail("bad_time", "Give a start time.")
    end = start + timedelta(minutes=service["durationMin"])
    fit = slot_fits(store, data.get("orgId"), start, end)
    if not fit["ok"]:
        return fit
    summary = booking_summary(service, person, start, service["price"])
    probe = {
        "orgId": data.get("orgId"),
        "customerId": data.get("customerId"),
        "serviceId": service["id"],
        "practitionerId": person["id"],
    }
    lock = lock_booking(store, {
        "orgId": data.get("orgId"),
        "practitionerId": person["id"],
        "customerId": data.get("customerId"),
        "startMs": epoch_ms(start),
        "endMs": epoch_ms(end),
        "ignoreBookingId": booking["id"],
    })
    if not lock["ok"]:
        lock["summary"] = summary
        lock["nearest"] = nearest_slots(store, probe, start)
        return lock
    if data.get("confirm") is not True:
        return fail(
            "confirm_required",
            "Show the service, practitioner, date, time, and price. Wait for a yes.",
            {"summary": summary},
        )
    again = lock_booking(store, {
        "orgId": data.get("orgId"),
        "practitionerId": person["id"],
        "customerId": data.get("customerId"),
        "startMs": epoch_ms(start),
        "endMs": epoch_ms(end),
        "ignoreBookingId": booking["id"],
    })
    if not again["ok"]:
        again["summary"] = summary
        again["nearest"] = nearest_slots(store, probe, start)
        return again
    booking["start"] = to_iso(start)
    booking["end"] = to_iso(end)
    booking["practitionerId"] = person["id"]
    booking["price"] = service["price"]
    return {"ok": True, "booking": booking, "summary": summary}


def cancel_booking(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    booking = next((row for row in store["bookings"] if row["id"] == data.get("bookingId")), None)
    if (
        not booking
        or booking["orgId"] != data.get("orgId")
        or booking["customerId"] != data.get("customerId")
        or booking["status"] != "booked"
    ):
        return fail("not_your_booking", "That booking is not yours.")
    service = service_row(store, data.get("orgId"), booking["serviceId"])
    person = practitioner_row(store, data.get("orgId"), booking["practitionerId"])
    start = as_utc(booking["start"])
    summary = booking_summary(service, person, start, booking["price"])
    if data.get("confirm") is not True:
        return fail("confirm_required", "Wait for a yes before cancelling this booking.", {"summary": summary})
    now = as_utc(data["now"]) if data.get("now") is not None else datetime.now(timezone.utc)
    hours_until = (epoch_ms(start) - epoch_ms(now)) / 3600000
    policy = store["bookingPolicy"]
    late = hours_until < policy["cancelFreeHours"]
    booking["status"] = "cancelled"
    knowledge = next(
        (
            row for row in store["knowledge"]
            if row["orgId"] == data.get("orgId")
            and row["document"] == policy["document"]
            and row["section"] == policy["section"]
        ),
        None,
    )
    return {
        "ok": True,
        "bookingId": booking["id"],
        "status": booking["status"],
        "feeRate": policy["lateFeeRate"] if late else 0,
        "document": policy["document"],
        "section": policy["section"],
        "policyText": knowledge["text"] if knowledge else "",
        "summary": summary,
    }


def list_my_bookings(store, data):
    gate = require_customer(store, data.get("orgId"), data.get("customerId"))
    if not gate["ok"]:
        return gate
    now = epoch_ms(datetime.now(timezone.utc))
    rows = [
        row for row in store["bookings"]
        if row["orgId"] == data.get("orgId") and row["customerId"] == data.get("customerId")
    ]

    def map_row(row):
        service = service_row(store, row["orgId"], row["serviceId"])
        return {
            "id": row["id"],
            "serviceId": row["serviceId"],
            "service": service["name"] if service else row["serviceId"],
            "practitionerId": row["practitionerId"],
            "start": row["start"],
            "end": row["end"],
            "price": row["price"],
            "status": row["status"],
            "when": "upcoming" if epoch_ms(row["end"]) >= now else "past",
        }

    return {
        "ok": True,
        "upcoming": [map_row(row) for row in rows if row["status"] == "booked" and epoch_ms(row["end"]) >= now],
        "past": [map_row(row) for row in rows if row["status"] != "booked" or epoch_ms(row["end"]) < now],
    }


def run_tool(store, action, ctx):
    org_id = ctx.get("sessionOrgId")
    customer_id = ctx.get("sessionCustomerId")
    args = ctx.get("args") or {}
    data = dict(args)
    data["orgId"] = org_id
    data["customerId"] = customer_id
    if action == "search_knowledge":
        return search_knowledge(store, {"orgId": org_id, "query": args.get("query") or args.get("text") or ""})
    if action == "search_products":
        return search_products(store, data)
    if action == "quote_order":
        return quote_order(store, data)
    if action == "create_order":
        return create_order(store, data)
    if action == "update_order":
        return update_order(store, data)
    if action == "cancel_order":
        return cancel_order(store, data)
    if action == "get_order_status":
        return get_order_status(store, data)
    if action == "list_my_orders":
        return list_my_orders(store, data)
    if action == "reorder":
        return reorder(store, data)
    if action == "list_services":
        return list_services(store, data)
    if action == "get_opening_hours":
        return get_opening_hours(store, data)
    if action == "find_available_slots":
        return find_available_slots(store, data)
    if action == "create_booking":
        return create_booking(store, data)
    if action == "reschedule_booking":
        return reschedule_booking(store, data)
    if action == "cancel_booking":
        return cancel_booking(store, data)
    if action == "list_my_bookings":
        return list_my_bookings(store, data)
    if action == "advance_order_status":
        return advance_order_status(store, data)
    return fail("unknown_tool", "That tool is not on this agent.")
