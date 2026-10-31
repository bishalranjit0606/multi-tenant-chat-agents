"""Advance a tea order status as a shop admin.

Example:
  DATABASE_URL=postgresql://shop:shop@localhost:5433/shop \\
  python -m shop.advance_order --order ord_nima_last --status confirmed
"""

from __future__ import annotations

import argparse
import os
import sys

from shop.auth import advance_order, login
from shop.db import DEV_PASSWORD


def main(argv=None):
    parser = argparse.ArgumentParser(description="Advance an order status (admin only).")
    parser.add_argument("--order", required=True, help="Order id, e.g. ord_nima_last")
    parser.add_argument(
        "--status",
        required=True,
        choices=["pending", "confirmed", "shipped", "delivered", "cancelled"],
    )
    parser.add_argument("--shop", default="tea", choices=["tea", "studio"])
    parser.add_argument("--email", default="admin@tea.com")
    parser.add_argument("--password", default=DEV_PASSWORD)
    args = parser.parse_args(argv)

    if not os.environ.get("DATABASE_URL", "").strip():
        print("Set DATABASE_URL first.", file=sys.stderr)
        return 1

    logged = login(None, args.shop, args.email, args.password)
    if not logged.get("ok"):
        print(logged.get("message") or "Login failed.", file=sys.stderr)
        return 1
    if logged.get("role") != "admin":
        print("That login is not an admin.", file=sys.stderr)
        return 1

    result = advance_order(None, logged["token"], args.order, args.status)
    if not result.get("ok"):
        print(result.get("message") or result.get("code") or "Advance failed.", file=sys.stderr)
        return 1
    print(f"{result['orderId']} -> {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
