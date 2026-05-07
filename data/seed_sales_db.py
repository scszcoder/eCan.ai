"""Seed a small SQLite ``sales.db`` for the ``query_sales_db`` MCP tool.

Run from the repo root:

    python data/seed_sales_db.py
    # or, to use a custom location matching ECAN_SALES_DB_PATH:
    python data/seed_sales_db.py --db "C:/path/to/sales.db"

The schema mirrors a tiny order-management system that's deliberately
similar to what the agent's ``query_sales_db`` tool will be asked about
in customer-service conversations: customers, products / inventory,
orders and their line items, plus shipments. Numbers are made up but
internally consistent (each order's ``total_cents`` matches the sum of
its line items, inventory ``stock_qty`` reflects the orders, etc.) so
SQL queries return believable answers during testing.

This script is idempotent: running it again rebuilds the same DB from
scratch. Existing files are renamed with a ``.bak-<timestamp>`` suffix
to make accidental data loss visible.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sqlite3
import sys


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    phone         TEXT,
    country       TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE inventory (
    sku           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    price_cents   INTEGER NOT NULL CHECK (price_cents >= 0),
    stock_qty     INTEGER NOT NULL CHECK (stock_qty >= 0),
    reorder_point INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE orders (
    order_id      TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id),
    status        TEXT NOT NULL CHECK (status IN (
                      'pending', 'paid', 'shipped', 'delivered',
                      'cancelled', 'refunded'
                  )),
    total_cents   INTEGER NOT NULL CHECK (total_cents >= 0),
    currency      TEXT NOT NULL DEFAULT 'USD',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE order_items (
    order_id        TEXT NOT NULL REFERENCES orders(order_id),
    line_no         INTEGER NOT NULL,
    sku             TEXT NOT NULL REFERENCES inventory(sku),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE shipments (
    shipment_id   TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders(order_id),
    carrier       TEXT NOT NULL,
    tracking      TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN (
                      'label_created', 'in_transit', 'out_for_delivery',
                      'delivered', 'returned'
                  )),
    shipped_at    TEXT,
    delivered_at  TEXT
);

CREATE INDEX idx_orders_customer       ON orders(customer_id);
CREATE INDEX idx_orders_status         ON orders(status);
CREATE INDEX idx_orders_created_at     ON orders(created_at);
CREATE INDEX idx_order_items_order     ON order_items(order_id);
CREATE INDEX idx_order_items_sku       ON order_items(sku);
CREATE INDEX idx_shipments_order       ON shipments(order_id);
CREATE INDEX idx_shipments_status      ON shipments(status);
CREATE INDEX idx_inventory_category    ON inventory(category);
"""


# --- Sample data ----------------------------------------------------------
# Prices are stored in cents (no float drift). Dates use ISO-8601 strings
# so SQLite's date functions work without extra conversion.

CUSTOMERS = [
    # customer_id, name, email, phone, country, created_at
    ("CUST-00001", "Alice Chen",        "alice@example.com",        "+1-415-555-0101", "US", "2025-08-12 10:14:00"),
    ("CUST-00002", "Bob Martinez",      "bob.m@example.com",        "+1-512-555-0119", "US", "2025-09-04 14:02:00"),
    ("CUST-00003", "Catherine Liu",     "catherine.liu@example.com", "+44-20-7946-0102", "UK", "2025-10-21 09:30:00"),
    ("CUST-00004", "Daniel Schmidt",    "daniel.s@example.de",      "+49-30-555-0177", "DE", "2025-11-09 16:45:00"),
    ("CUST-00005", "Emma O'Connor",     "emma.oc@example.com",      "+353-1-555-0143", "IE", "2026-01-15 11:08:00"),
    ("CUST-00006", "Frank Watanabe",    "frank.w@example.jp",       "+81-3-5555-0190", "JP", "2026-02-28 22:11:00"),
    ("CUST-00007", "Grace Park",        "grace.park@example.kr",    "+82-2-555-0157", "KR", "2026-03-12 04:33:00"),
]

# (sku, name, category, price_cents, stock_qty, reorder_point)
INVENTORY = [
    ("PRO-MAX-2026-128", "Pro Max 2026 (128 GB)",  "phone",      129900, 42, 10),
    ("PRO-MAX-2026-256", "Pro Max 2026 (256 GB)",  "phone",      149900, 18, 10),
    ("PRO-MAX-2026-512", "Pro Max 2026 (512 GB)",  "phone",      179900,  6,  5),
    ("ECAN-CASE-PMX",    "eCan Case for Pro Max",  "accessory",    3900, 240, 50),
    ("ECAN-CHARGER-65W", "eCan 65W USB-C Charger", "accessory",    4900, 130, 30),
    ("ECAN-EARBUDS-PRO", "eCan Earbuds Pro",       "accessory",   24900,  44, 20),
    ("ECAN-WATCH-S2",    "eCan Watch Series 2",    "wearable",    39900,  12,  6),
    ("ECAN-CABLE-USBC",  "eCan USB-C Cable 1.5m",  "accessory",    1500, 510, 100),
]

# (order_id, customer_id, status, currency, created_at, updated_at, [(sku, qty, unit_price_cents), ...])
ORDERS = [
    ("ORD-202508-0001", "CUST-00001", "delivered", "USD", "2025-08-15 12:01:00", "2025-08-19 18:43:00",
        [("PRO-MAX-2026-128", 1, 129900), ("ECAN-CASE-PMX", 1, 3900)]),
    ("ORD-202509-0042", "CUST-00002", "delivered", "USD", "2025-09-09 09:22:00", "2025-09-13 14:07:00",
        [("ECAN-EARBUDS-PRO", 2, 24900), ("ECAN-CABLE-USBC", 3, 1500)]),
    ("ORD-202510-0099", "CUST-00003", "shipped", "GBP", "2025-10-25 17:05:00", "2025-10-27 08:12:00",
        [("PRO-MAX-2026-256", 1, 149900), ("ECAN-CHARGER-65W", 1, 4900)]),
    ("ORD-202511-0177", "CUST-00004", "paid", "EUR", "2025-11-14 11:31:00", "2025-11-14 11:33:00",
        [("ECAN-WATCH-S2", 1, 39900)]),
    ("ORD-202601-0033", "CUST-00005", "cancelled", "USD", "2026-01-20 15:50:00", "2026-01-21 09:14:00",
        [("PRO-MAX-2026-512", 1, 179900)]),
    ("ORD-202602-0210", "CUST-00006", "refunded", "JPY", "2026-02-29 03:15:00", "2026-03-04 21:00:00",
        # JPY has no minor units; we still store amount in the smallest accounting unit (yen) for consistency.
        [("ECAN-EARBUDS-PRO", 1, 24900)]),
    ("ORD-202603-0301", "CUST-00007", "pending", "KRW", "2026-03-13 08:09:00", "2026-03-13 08:09:00",
        [("PRO-MAX-2026-128", 1, 129900), ("ECAN-EARBUDS-PRO", 1, 24900), ("ECAN-CABLE-USBC", 2, 1500)]),
    ("ORD-202604-0411", "CUST-00001", "shipped", "USD", "2026-04-22 19:44:00", "2026-04-23 06:30:00",
        [("ECAN-CHARGER-65W", 2, 4900), ("ECAN-CABLE-USBC", 4, 1500)]),
]

# (shipment_id, order_id, carrier, tracking, status, shipped_at, delivered_at)
SHIPMENTS = [
    ("SHP-1001", "ORD-202508-0001", "UPS",    "1Z9X12345678901234", "delivered",        "2025-08-16 09:00:00", "2025-08-19 18:30:00"),
    ("SHP-1002", "ORD-202509-0042", "FedEx",  "FDX774488221199",     "delivered",        "2025-09-10 11:20:00", "2025-09-13 13:55:00"),
    ("SHP-1003", "ORD-202510-0099", "DHL",    "JD0143997744123",     "in_transit",       "2025-10-26 13:00:00", None),
    ("SHP-1004", "ORD-202604-0411", "UPS",    "1Z9X12345678905555", "out_for_delivery", "2026-04-23 07:00:00", None),
]


def _build_db(db_path: str) -> None:
    db_dir = os.path.dirname(db_path) or "."
    os.makedirs(db_dir, exist_ok=True)

    if os.path.exists(db_path):
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{db_path}.bak-{ts}"
        shutil.move(db_path, backup)
        print(f"[seed] Existing DB backed up to: {backup}")

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)

        with conn:
            conn.executemany(
                "INSERT INTO customers (customer_id, name, email, phone, country, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                CUSTOMERS,
            )
            conn.executemany(
                "INSERT INTO inventory (sku, name, category, price_cents, stock_qty, reorder_point) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                INVENTORY,
            )

            for order in ORDERS:
                order_id, customer_id, status, currency, created_at, updated_at, lines = order
                total_cents = sum(qty * unit_price for _, qty, unit_price in lines)
                conn.execute(
                    "INSERT INTO orders (order_id, customer_id, status, total_cents, "
                    "currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (order_id, customer_id, status, total_cents, currency, created_at, updated_at),
                )
                for line_no, (sku, qty, unit_price) in enumerate(lines, start=1):
                    conn.execute(
                        "INSERT INTO order_items (order_id, line_no, sku, quantity, "
                        "unit_price_cents) VALUES (?, ?, ?, ?, ?)",
                        (order_id, line_no, sku, qty, unit_price),
                    )

            conn.executemany(
                "INSERT INTO shipments (shipment_id, order_id, carrier, tracking, "
                "status, shipped_at, delivered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                SHIPMENTS,
            )

        # Sanity checks: recomputed totals + a quick row count summary.
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM customers")
        n_customers = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM inventory")
        n_inventory = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orders")
        n_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM order_items")
        n_items = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM shipments")
        n_shipments = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(total_cents), 0) FROM orders WHERE status NOT IN ('cancelled','refunded')")
        revenue_cents = cur.fetchone()[0]
    finally:
        conn.close()

    print(f"[seed] Wrote: {db_path}")
    print(f"[seed]   customers:   {n_customers}")
    print(f"[seed]   inventory:   {n_inventory}")
    print(f"[seed]   orders:      {n_orders}")
    print(f"[seed]   order_items: {n_items}")
    print(f"[seed]   shipments:   {n_shipments}")
    print(f"[seed]   net revenue (excl. cancelled/refunded): {revenue_cents/100:.2f} mixed-currency units")
    print()
    print("Try a query (read-only — exactly what the agent will run):")
    print("  python -c \"import sqlite3; c=sqlite3.connect(r'%s'); "
          "[print(r) for r in c.execute('SELECT order_id,status,total_cents FROM orders ORDER BY created_at DESC')]\""
          % db_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    default_db = os.environ.get("ECAN_SALES_DB_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sales.db"
    )
    parser.add_argument(
        "--db",
        default=default_db,
        help=(
            "Output SQLite path. Defaults to ECAN_SALES_DB_PATH if set, "
            "otherwise '<repo>/data/sales.db'."
        ),
    )
    args = parser.parse_args(argv)

    _build_db(args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
