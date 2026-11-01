import copy
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shop.rules import (
    TIME_ZONE,
    advance_order_status,
    cancel_booking,
    cancel_order,
    choose_state,
    create_booking,
    create_order,
    create_store,
    find_available_slots,
    get_order_status,
    kathmandu_to_utc,
    list_my_orders,
    quote_order,
    reorder,
    reschedule_booking,
    resolve_phrase,
    run_tool,
    search_knowledge,
    to_iso,
    update_order,
)
from shop.seed import seed

SLOT_START = to_iso(kathmandu_to_utc(2026, 11, 3, 10, 0))
OVERLAP_START = to_iso(kathmandu_to_utc(2026, 11, 3, 10, 30))
LATER_START = to_iso(kathmandu_to_utc(2026, 11, 3, 14, 0))
NOW = datetime(2026, 10, 30, 6, 15, tzinfo=timezone.utc)


def snap(store):
    return copy.deepcopy(store)


def product(store, sku):
    return next(row for row in store["products"] if row["sku"] == sku)


def test_seed_has_the_promised_rows():
    assert len(seed["products"]) >= 20
    assert len(seed["services"]) >= 6
    assert len(seed["practitioners"]) == 3
    assert len(seed["hours"]) == 7
    assert len(seed["holidays"]) >= 1
    assert len([row for row in seed["customers"] if row["orgId"] == "org_a"]) == 3
    assert len([row for row in seed["customers"] if row["orgId"] == "org_b"]) == 3
    assert len([row for row in seed["orders"] if row["customerId"] == "a_nima"]) >= 1
    assert len([row for row in seed["orders"] if row["customerId"] == "a_sita"]) >= 1
    assert len([row for row in seed["bookings"] if row["customerId"] == "b_maya"]) >= 1
    assert len([row for row in seed["bookings"] if row["customerId"] == "b_arun"]) >= 1
    assert len([row for row in seed["knowledge"] if row["orgId"] == "org_a"]) >= 15
    assert len([row for row in seed["knowledge"] if row["orgId"] == "org_b"]) >= 15
    assert len([
        row for row in seed["knowledge"]
        if row["orgId"] == "org_a" and row["document"] == "FAQ"
    ]) >= 15
    assert len([
        row for row in seed["knowledge"]
        if row["orgId"] == "org_b" and row["document"] == "FAQ"
    ]) >= 15


def test_quote_does_not_save():
    store = create_store(seed)
    before = snap(store)
    quote = quote_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
    })
    assert quote["ok"] is True
    assert quote["summary"]["total"] == 900
    assert quote["summary"]["payment"] == "cash_on_delivery"
    assert store == before


def test_create_waits_for_confirm():
    store = create_store(seed)
    before = snap(store)
    held = create_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
        "confirm": False,
    })
    assert held["ok"] is False
    assert held["code"] == "confirm_required"
    assert held["summary"]["items"][0]["unitPrice"] == 450
    assert store == before


def test_create_saves_a_pending_cash_order_and_holds_stock():
    store = create_store(seed)
    made = create_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
        "confirm": True,
    })
    assert made["ok"] is True
    assert made["order"]["status"] == "pending"
    assert made["order"]["payment"] == "cash_on_delivery"
    assert made["order"]["total"] == 900
    assert product(store, "TEA-JAS-50")["stock"] == 18


def test_quantity_over_stock_is_refused_and_another_product_is_offered():
    store = create_store(seed)
    before = snap(store)
    denied = create_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-ILAM-100", "qty": 2}],
        "confirm": True,
    })
    assert denied["ok"] is False
    assert denied["code"] == "insufficient_stock"
    assert denied["problems"][0]["have"] == 1
    assert denied["problems"][0]["alternative"]["category"] == "black"
    assert denied["problems"][0]["alternative"]["stock"] >= 2
    assert denied["problems"][0]["alternative"]["sku"] != "TEA-ILAM-100"
    assert store == before


def test_shipped_orders_cannot_be_edited_or_cancelled():
    store = create_store(seed)
    made = create_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 1}],
        "confirm": True,
    })
    advance_order_status(store, {"orgId": "org_a", "orderId": made["order"]["id"], "status": "shipped"})
    edited = update_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
        "confirm": True,
    })
    cancelled = cancel_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "confirm": True,
    })
    saved = next(row for row in store["orders"] if row["id"] == made["order"]["id"])
    assert edited["code"] == "not_pending"
    assert edited["status"] == "shipped"
    assert re.search(r"shipped", edited["message"])
    assert cancelled["code"] == "not_pending"
    assert cancelled["status"] == "shipped"
    assert saved["status"] == "shipped"
    assert saved["items"][0]["qty"] == 1


def test_pending_update_and_cancel_need_a_yes_then_they_stick():
    store = create_store(seed)
    made = create_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 1}],
        "confirm": True,
    })
    preview = update_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "address": "New road",
        "confirm": False,
    })
    assert preview["code"] == "confirm_required"
    assert next(row for row in store["orders"] if row["id"] == made["order"]["id"])["address"] == "Bhaktapur"
    edited = update_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
        "confirm": True,
    })
    assert edited["ok"] is True
    assert edited["order"]["items"][0]["qty"] == 2
    assert product(store, "TEA-JAS-50")["stock"] == 18
    no_cancel = cancel_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "confirm": False,
    })
    assert no_cancel["code"] == "confirm_required"
    assert next(row for row in store["orders"] if row["id"] == made["order"]["id"])["status"] == "pending"
    cancelled = cancel_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "orderId": made["order"]["id"],
        "confirm": True,
    })
    assert cancelled["ok"] is True
    assert next(row for row in store["orders"] if row["id"] == made["order"]["id"])["status"] == "cancelled"
    assert product(store, "TEA-JAS-50")["stock"] == 20


def test_a_customer_only_sees_their_own_orders():
    store = create_store(seed)
    listing = list_my_orders(store, {"orgId": "org_a", "customerId": "a_nima"})
    assert listing["orders"][0]["id"] == "ord_nima_last"
    assert all(row["id"].startswith("ord_nima") for row in listing["orders"])
    hidden = get_order_status(store, {"orgId": "org_a", "customerId": "a_nima", "orderId": "ord_sita_1"})
    assert hidden["code"] == "not_your_order"
    assert "orderId" not in hidden


def test_same_as_last_time_notes_price_and_stock_and_does_not_save_early():
    store = create_store(seed)
    before = len(store["orders"])
    blocked = reorder(store, {"orgId": "org_a", "customerId": "a_nima", "confirm": True})
    assert blocked["code"] == "insufficient_stock"
    assert any(note["type"] == "price" and note["from"] == 480 and note["to"] == 520 for note in blocked["notes"])
    assert any(note["type"] == "stock" and note["need"] == 2 and note["have"] == 1 for note in blocked["notes"])
    assert len(store["orders"]) == before
    preview = reorder(store, {"orgId": "org_a", "customerId": "a_sita", "confirm": False})
    assert preview["code"] == "confirm_required"
    assert any(note["type"] == "price" and note["from"] == 400 and note["to"] == 450 for note in preview["notes"])
    assert len(store["orders"]) == before
    made = reorder(store, {"orgId": "org_a", "customerId": "a_sita", "confirm": True})
    assert made["ok"] is True
    assert made["order"]["status"] == "pending"
    assert made["order"]["items"][0]["unitPrice"] == 450
    assert made["order"]["payment"] == "cash_on_delivery"


def test_knowledge_names_the_document_and_stays_in_the_org():
    store = create_store(seed)
    tea = search_knowledge(store, {"orgId": "org_a", "query": "return unopened tea window"})
    assert len(tea["matches"]) >= 1
    assert isinstance(tea["matches"][0]["document"], str)
    assert isinstance(tea["matches"][0]["section"], str)
    assert all(row["document"] != "Policies" for row in tea["matches"])
    leak = search_knowledge(store, {"orgId": "org_a", "query": "physiotherapy prenatal practitioner"})
    assert len(leak["matches"]) == 0
    studio = run_tool(store, "search_knowledge", {
        "sessionOrgId": "org_b",
        "sessionCustomerId": "b_lina",
        "args": {"query": "cancellation fee hours", "orgId": "org_a"},
    })
    assert any(row["document"] == "Policies" and row["section"] == "Cancellation" for row in studio["matches"])
    assert all("Himali Tea House" not in row["text"] for row in studio["matches"])
    stored = search_knowledge(store, {"orgId": "org_a", "query": "How do I store the tea?"})
    assert stored["matches"][0]["document"] == "FAQ"
    assert stored["matches"][0]["section"] == "Storage"


def test_a_new_order_gets_a_real_id_when_seq_is_missing():
    bare = copy.deepcopy(seed)
    bare.pop("seq", None)
    made = create_order(bare, {
        "orgId": "org_a",
        "customerId": "a_nima",
        "items": [{"sku": "TEA-JAS-50", "qty": 1}],
        "confirm": True,
    })
    assert made["ok"] is True
    assert made["order"]["id"] == "ord_101"


def test_session_org_wins_over_a_tool_argument():
    store = create_store(seed)
    crossed = run_tool(store, "create_order", {
        "sessionOrgId": "org_b",
        "sessionCustomerId": "a_nima",
        "args": {
            "items": [{"sku": "TEA-JAS-50", "qty": 1}],
            "confirm": True,
            "orgId": "org_a",
            "customerId": "a_nima",
        },
    })
    assert crossed["code"] == "wrong_org"
    assert len(store["orders"]) == len(seed["orders"])
    products = run_tool(store, "search_products", {
        "sessionOrgId": "org_a",
        "sessionCustomerId": "a_nima",
        "args": {"orgId": "org_b", "query": "massage"},
    })
    assert len(products["products"]) == 0


def test_next_tuesday_afternoon_is_14_00_in_kathmandu():
    resolved = resolve_phrase("next Tuesday afternoon", NOW)
    assert resolved["ok"] is True
    assert resolved["timeZone"] == TIME_ZONE
    assert TIME_ZONE == "Asia/Kathmandu"
    assert resolved["weekday"] == "Tue"
    assert resolved["hour"] == 14
    assert resolved["local"] == "2026-11-03 14:00"
    assert resolved["start"] == "2026-11-03T08:15:00.000Z"
    store = create_store(seed)
    slots = find_available_slots(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "Swedish massage",
        "practitionerId": "Anita",
        "phrase": "next Tuesday afternoon",
        "now": NOW,
    })
    assert slots["ok"] is True
    assert slots["slots"][0]["local"] == "2026-11-03 14:00"
    assert slots["slots"][0]["practitionerName"] == "Anita"
    booked = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "Swedish massage",
        "practitionerId": "Anita",
        "phrase": "next Tuesday afternoon",
        "now": NOW,
        "confirm": True,
    })
    assert booked["ok"] is True
    again = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "Swedish massage",
        "practitionerId": "Anita",
        "phrase": "next Tuesday afternoon",
        "now": NOW,
        "confirm": True,
    })
    assert again["ok"] is False
    assert again["code"] == "slot_taken"


def test_plain_phrases_resolve_in_kathmandu():
    cases = {
        "nov 5 2 pm": "2026-11-05 14:00",
        "next wednesday 2 pm": "2026-11-04 14:00",
        "4 30 noon": "2026-10-30 16:30",
        "2026-11-05 14:00": "2026-11-05 14:00",
        "5th november 10:30 am": "2026-11-05 10:30",
        "next wednesday": "2026-11-04",
    }
    for phrase, local in cases.items():
        resolved = resolve_phrase(phrase, NOW)
        assert resolved["ok"] is True, phrase
        assert resolved["local"] == local, phrase
    assert resolve_phrase("list available slots", NOW)["code"] == "unparsed_phrase"
    store = create_store(seed)
    exact = find_available_slots(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "phrase": "nov 5 2 pm",
        "now": NOW,
    })
    assert exact["requested"] == "2026-11-05 14:00"
    assert exact["requestedFree"] is True
    assert all(slot["local"].startswith("2026-11-05") for slot in exact["slots"])
    assert exact["slots"][0]["localEnd"] == "2026-11-05 10:00"
    week = find_available_slots(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "now": NOW,
    })
    assert len(week["freeDays"]) >= 5
    assert all(slot["start"] > to_iso(NOW) for slot in week["slots"])


def test_the_newest_saved_shop_wins():
    stale = create_store(seed)
    fresh = create_store(seed)
    fresh["seq"] = 101
    fresh["orders"].append({"id": "ord_101", "orgId": "org_a", "customerId": "a_nima", "status": "pending"})
    picked = choose_state([
        {"store": stale, "sessions": {"chat": {"orgId": "org_a", "customerId": "a_nima"}}, "savedAt": 1},
        {"store": fresh, "sessions": {"chat": {"orgId": "org_b", "customerId": "b_maya"}}, "savedAt": 2},
    ], seed)
    assert any(row["id"] == "ord_101" for row in picked["store"]["orders"])
    assert picked["sessions"]["chat"]["orgId"] == "org_b"


def test_slots_must_fit_hours_holidays_and_service_length():
    store = create_store(seed)
    early = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": to_iso(kathmandu_to_utc(2026, 11, 3, 8, 0)),
        "confirm": True,
    })
    holiday = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": to_iso(kathmandu_to_utc(2026, 11, 8, 10, 0)),
        "confirm": True,
    })
    short = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": to_iso(kathmandu_to_utc(2026, 11, 3, 17, 30)),
        "confirm": True,
    })
    assert early["code"] == "outside_hours"
    assert holiday["code"] == "holiday"
    assert short["code"] == "too_short"
    assert len(store["bookings"]) == len(seed["bookings"])


def test_booking_waits_for_confirm_and_find_available_slots_stays_read_only():
    store = create_store(seed)
    before = snap(store)
    slots = find_available_slots(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "from": "2026-11-03",
        "to": "2026-11-03",
    })
    assert slots["timeZone"] == "Asia/Kathmandu"
    assert any(row["start"] == SLOT_START and row["price"] == 2500 for row in slots["slots"])
    assert store == before
    preview = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": SLOT_START,
        "confirm": False,
    })
    assert preview["code"] == "confirm_required"
    assert preview["summary"]["service"] == "Swedish massage"
    assert preview["summary"]["practitioner"] == "Anita"
    assert preview["summary"]["price"] == 2500
    assert store == before


def test_one_slot_cannot_be_booked_twice_and_a_customer_cannot_overlap():
    store = create_store(seed)
    first = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": SLOT_START,
        "confirm": True,
    })
    second = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_arun",
        "serviceId": "svc_deep",
        "practitionerId": "p_anita",
        "start": SLOT_START,
        "confirm": True,
    })
    self_booking = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "svc_yoga",
        "practitionerId": "p_binod",
        "start": OVERLAP_START,
        "confirm": True,
    })
    assert first["ok"] is True
    assert second["code"] == "slot_taken"
    assert len(second["nearest"]) >= 1
    assert all(row["start"] != SLOT_START for row in second["nearest"])
    assert self_booking["code"] == "customer_busy"
    booked = [row for row in store["bookings"] if row["status"] == "booked" and row["start"] == SLOT_START]
    assert len(booked) == 1
    open_slots = find_available_slots(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "from": "2026-11-03",
        "to": "2026-11-03",
    })
    assert all(row["start"] != SLOT_START for row in open_slots["slots"])


def test_a_conflicting_move_is_refused_and_the_booking_stays():
    store = create_store(seed)
    maya = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": SLOT_START,
        "confirm": True,
    })
    lina = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": LATER_START,
        "confirm": True,
    })
    assert lina["ok"] is True
    moved = reschedule_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "bookingId": maya["booking"]["id"],
        "start": LATER_START,
        "confirm": True,
    })
    assert moved["ok"] is False
    assert moved["code"] == "slot_taken"
    assert len(moved["nearest"]) >= 1
    assert next(row for row in store["bookings"] if row["id"] == maya["booking"]["id"])["start"] == SLOT_START
    quiet = reschedule_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "bookingId": maya["booking"]["id"],
        "start": OVERLAP_START,
        "confirm": False,
    })
    assert quiet["code"] == "confirm_required"
    assert next(row for row in store["bookings"] if row["id"] == maya["booking"]["id"])["start"] == SLOT_START
    done = reschedule_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "bookingId": maya["booking"]["id"],
        "start": OVERLAP_START,
        "confirm": True,
    })
    assert done["ok"] is True
    assert done["summary"]["price"] == 2500
    assert next(row for row in store["bookings"] if row["id"] == maya["booking"]["id"])["start"] == OVERLAP_START


def test_cancel_applies_the_12_hour_policy_and_cites_the_section():
    store = create_store(seed)
    booking = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": SLOT_START,
        "confirm": True,
    })
    early_now = datetime.fromtimestamp(
        datetime.fromisoformat(SLOT_START.replace("Z", "+00:00")).timestamp() - 2 * 60 * 60,
        timezone.utc,
    )
    late = cancel_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "bookingId": booking["booking"]["id"],
        "confirm": True,
        "now": early_now.isoformat(),
    })
    assert late["feeRate"] == 0.5
    assert late["document"] == "Policies"
    assert late["section"] == "Cancellation"
    assert re.search(r"12 hours", late["policyText"])
    again = create_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "serviceId": "svc_swedish",
        "practitionerId": "p_anita",
        "start": LATER_START,
        "confirm": True,
    })
    free_now = datetime.fromtimestamp(
        datetime.fromisoformat(LATER_START.replace("Z", "+00:00")).timestamp() - 20 * 60 * 60,
        timezone.utc,
    )
    free = cancel_booking(store, {
        "orgId": "org_b",
        "customerId": "b_lina",
        "bookingId": again["booking"]["id"],
        "confirm": True,
        "now": free_now.isoformat(),
    })
    assert free["feeRate"] == 0
    other = cancel_booking(store, {
        "orgId": "org_b",
        "customerId": "b_maya",
        "bookingId": again["booking"]["id"],
        "confirm": True,
    })
    assert other["code"] == "not_your_booking"
