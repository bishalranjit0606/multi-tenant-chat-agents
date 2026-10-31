import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shop.auth import login, logout, read_shop, session_for, signup
from shop.db import DEV_PASSWORD, connect, load_store, seed_database
from shop.rules import get_order_status, quote_order


def fresh_db(tmp_path):
    return seed_database(tmp_path / "shop.db")


def test_loaded_store_keeps_rule_results(tmp_path):
    path = fresh_db(tmp_path)
    store = load_store(path)
    quote = quote_order(store, {
        "orgId": "org_a",
        "customerId": "a_ram",
        "items": [{"sku": "TEA-JAS-50", "qty": 2}],
    })
    assert quote["ok"] is True
    assert quote["summary"]["total"] == 900
    status = get_order_status(store, {"orgId": "org_a", "customerId": "a_sita", "orderId": "ord_sita_1"})
    assert status["ok"] is True
    assert status["total"] == 400


def test_signup_shop_comes_from_the_entry_and_role_stays_customer(tmp_path):
    path = fresh_db(tmp_path)
    tea = signup(
        path, "tea", "new.tea@himali.test", "secret-1", "New Tea", "Bhaktapur",
        org_id="org_b", role="admin",
    )
    studio = signup(
        path, "studio", "new.studio@lotus.test", "secret-2", "New Studio", "Pokhara",
        org_id="org_a", role="admin",
    )
    assert tea["ok"] is True
    assert tea["orgId"] == "org_a"
    assert tea["role"] == "customer"
    assert studio["orgId"] == "org_b"
    assert studio["role"] == "customer"
    conn = connect(path)
    try:
        tea_row = conn.execute("SELECT org_id, role FROM users WHERE email = ?", ("new.tea@himali.test",)).fetchone()
        studio_row = conn.execute(
            "SELECT org_id, role FROM users WHERE email = ?",
            ("new.studio@lotus.test",),
        ).fetchone()
    finally:
        conn.close()
    assert tea_row["org_id"] == "org_a"
    assert tea_row["role"] == "customer"
    assert studio_row["org_id"] == "org_b"
    assert studio_row["role"] == "customer"


def test_login_returns_a_token_and_logout_kills_it(tmp_path):
    path = fresh_db(tmp_path)
    signed = login(path, "tea", "nima@himali.test", DEV_PASSWORD)
    assert signed["ok"] is True
    assert isinstance(signed["token"], str)
    assert signed["token"]
    assert session_for(path, signed["token"])["customerId"] == "a_nima"
    logout(path, signed["token"])
    assert session_for(path, signed["token"]) is None
    blocked = read_shop(path, signed["token"], "list_my_orders", {})
    assert blocked["ok"] is False
    assert blocked["code"] == "logged_out"


def test_tea_user_cannot_list_studio_bookings(tmp_path):
    path = fresh_db(tmp_path)
    token = login(path, "tea", "nima@himali.test", DEV_PASSWORD)["token"]
    listed = read_shop(path, token, "list_my_bookings", {"orgId": "org_b", "customerId": "b_maya"})
    rows = listed.get("upcoming", []) + listed.get("past", [])
    ids = [row["id"] for row in rows]
    assert "book_maya_past" not in ids
    assert "book_arun_past" not in ids


def test_nima_cannot_read_sitas_order(tmp_path):
    path = fresh_db(tmp_path)
    token = login(path, "tea", "nima@himali.test", DEV_PASSWORD)["token"]
    hidden = read_shop(path, token, "get_order_status", {
        "orgId": "org_a",
        "customerId": "a_sita",
        "orderId": "ord_sita_1",
    })
    assert hidden["code"] == "not_your_order"
    assert "orderId" not in hidden


def test_fake_org_id_does_not_switch_the_session_shop(tmp_path):
    path = fresh_db(tmp_path)
    token = login(path, "tea", "nima@himali.test", DEV_PASSWORD)["token"]
    services = read_shop(path, token, "list_services", {"orgId": "org_b", "customerId": "b_maya"})
    assert services["ok"] is True
    assert services["services"] == []
    products = read_shop(path, token, "search_products", {"orgId": "org_b", "query": ""})
    assert any(row["sku"] == "TEA-JAS-50" for row in products["products"])


def test_password_column_is_not_the_plain_dev_password(tmp_path):
    path = fresh_db(tmp_path)
    conn = connect(path)
    try:
        hashes = [row["password_hash"] for row in conn.execute("SELECT password_hash FROM users")]
        tables = [
            row["table_name"]
            for row in conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
                """
            )
        ]
        stored = []
        for table in tables:
            columns = [
                row["column_name"]
                for row in conn.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = ?
                      AND udt_name IN ('text', 'varchar')
                    """,
                    (table,),
                )
            ]
            if not columns:
                continue
            picked = ", ".join(f'"{name}"' for name in columns)
            for row in conn.execute(f'SELECT {picked} FROM "{table}"'):
                stored.extend(str(value) for value in row.values() if value is not None)
    finally:
        conn.close()
    assert len(hashes) == 4
    for saved in hashes:
        assert saved != DEV_PASSWORD
        assert DEV_PASSWORD not in saved
        assert saved.startswith("$2")
    assert DEV_PASSWORD.encode("utf-8") not in "\n".join(stored).encode("utf-8")
