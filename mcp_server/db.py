"""Read-only database access for the Campus Customs MCP server.

Everything here reads from the working copy of the database. Nothing in this
file invents values: if a row isn't there, the caller gets a "found: False"
result instead of a guess.
"""

import sqlite3
from pathlib import Path

# mcp_server/db.py -> HW5/ -> HW5/data/campus_customs_new.db
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"


def _connect() -> sqlite3.Connection:
    """Open the working copy read-only so a tool can't change shop data."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Problem 2 creates it by copying campus_customs.db."
        )
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _one(sql: str, params: tuple = ()) -> dict | None:
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _all(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# --- desk -------------------------------------------------------------------

def get_desk_date() -> str:
    """The date the shop is operating on. Used instead of the real clock."""
    row = _one("SELECT date_today FROM desk LIMIT 1")
    return row["date_today"] if row else ""


# --- inventory --------------------------------------------------------------

def get_stock(sku: str, size: str) -> dict | None:
    """One inventory row. Needs both sku and size, since that's the primary key."""
    return _one(
        "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size),
    )


def get_sizes_for_sku(sku: str) -> list[dict]:
    """Every size on record for a sku, so a short order can suggest alternatives."""
    return _all(
        "SELECT size, qty, location FROM inventory WHERE sku = ? ORDER BY qty DESC",
        (sku,),
    )


# --- tickets ----------------------------------------------------------------

TICKET_COLS = (
    "id, type, requester, subject, sku, size, qty, lease_id, invoice_id, "
    "status, notes, created_at"
)


def list_tickets(status: str | None = None) -> list[dict]:
    if status:
        return _all(
            f"SELECT {TICKET_COLS} FROM tickets WHERE status = ? ORDER BY id", (status,)
        )
    return _all(f"SELECT {TICKET_COLS} FROM tickets ORDER BY id")


def get_ticket(ticket_id: int) -> dict | None:
    return _one(f"SELECT {TICKET_COLS} FROM tickets WHERE id = ?", (ticket_id,))


# --- leases -----------------------------------------------------------------

def get_lease(lease_id: int) -> dict | None:
    return _one(
        "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
        "FROM leases WHERE id = ?",
        (lease_id,),
    )


# --- cash_accounts ----------------------------------------------------------

def get_cash_account(name: str = "checking") -> dict | None:
    return _one(
        "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (name,)
    )


# --- pricing ----------------------------------------------------------------

def get_pricing(sku: str) -> dict | None:
    return _one(
        "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
    )


# --- invoices ---------------------------------------------------------------

def get_invoice(invoice_id: int) -> dict | None:
    return _one(
        "SELECT id, vendor_id, amount, due_date, status, description "
        "FROM invoices WHERE id = ?",
        (invoice_id,),
    )


def list_invoices(status: str | None = None) -> list[dict]:
    if status:
        return _all(
            "SELECT id, vendor_id, amount, due_date, status, description "
            "FROM invoices WHERE status = ? ORDER BY due_date",
            (status,),
        )
    return _all(
        "SELECT id, vendor_id, amount, due_date, status, description "
        "FROM invoices ORDER BY due_date"
    )


# --- vendors ----------------------------------------------------------------

def get_vendor(vendor_id: int) -> dict | None:
    return _one(
        "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
    )


def list_vendors() -> list[dict]:
    return _all("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")


# --- payments ---------------------------------------------------------------

def list_payments() -> list[dict]:
    return _all(
        "SELECT id, kind, ref_id, amount, account, paid_at, approved_by "
        "FROM payments ORDER BY id"
    )


# --- helpers ----------------------------------------------------------------

def days_between(start: str, end: str) -> int | None:
    """Whole days from start to end, both as YYYY-MM-DD. None if either is bad."""
    from datetime import date

    try:
        a = date.fromisoformat(start[:10])
        b = date.fromisoformat(end[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days
