"""The only code that writes to the Campus Customs working database.

None of this is registered as an MCP tool, so no agent can reach it. It is
called by two backend routes, and only after a person acts:

  execute_payment      a human clicked approve on a prepared payment
  set_ticket_status    a ticket finished (or a payment for it was approved)
  reset_working_copy   a human asked for a fresh run

Every payment runs in one transaction that re-reads the amount, checks the
balance, and refuses anything that would take the account below zero.
"""

import calendar
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timezone

from .db import DB_PATH

ORIGINAL_DB = DB_PATH.parent / "campus_customs.db"


class PaymentError(Exception):
    """The payment can't go through. Nothing was changed."""


class InsufficientFunds(PaymentError):
    def __init__(self, balance: float, amount: float):
        self.balance = balance
        self.amount = amount
        super().__init__(
            f"Refused: paying ${amount:,.2f} would take checking from "
            f"${balance:,.2f} to ${balance - amount:,.2f}."
        )


def _connect() -> sqlite3.Connection:
    # isolation_level=None so BEGIN IMMEDIATE / COMMIT are under our control.
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def _add_month(day: str) -> str:
    y, m, d = (int(x) for x in day[:10].split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-{min(d, calendar.monthrange(y, m)[1]):02d}"


def _amount_for(conn: sqlite3.Connection, kind: str, target: dict) -> tuple[float, int | None]:
    """Look up what a payment costs right now. Returns (amount, ref_id)."""
    if kind == "invoice":
        inv = conn.execute(
            "SELECT id, amount, status FROM invoices WHERE id = ?", (target.get("invoice_id"),)
        ).fetchone()
        if inv is None:
            raise PaymentError(f"No invoice with id {target.get('invoice_id')}.")
        if inv["status"].lower() != "open":
            raise PaymentError(f"Invoice {inv['id']} is already {inv['status']}.")
        return inv["amount"], inv["id"]

    if kind == "rent":
        lease = conn.execute(
            "SELECT id, monthly_rent FROM leases WHERE id = ?", (target.get("lease_id"),)
        ).fetchone()
        if lease is None:
            raise PaymentError(f"No lease with id {target.get('lease_id')}.")
        return lease["monthly_rent"], lease["id"]

    if kind == "purchase":
        qty = target.get("qty") or 0
        if qty <= 0:
            raise PaymentError("A purchase needs a positive qty.")
        price = conn.execute(
            "SELECT unit_cost FROM pricing WHERE sku = ?", (target.get("sku"),)
        ).fetchone()
        stock = conn.execute(
            "SELECT 1 FROM inventory WHERE sku = ? AND size = ?",
            (target.get("sku"), target.get("size")),
        ).fetchone()
        vendor = conn.execute(
            "SELECT id FROM vendors WHERE id = ?", (target.get("vendor_id"),)
        ).fetchone()
        if price is None or stock is None or vendor is None:
            raise PaymentError("Purchase refers to a sku, size, or vendor that isn't in the database.")
        # payments.ref_id holds the vendor for a purchase.
        return round(price["unit_cost"] * qty, 2), vendor["id"]

    raise PaymentError(f"Unknown payment kind {kind!r}.")


def execute_payment(
    kind: str,
    target: dict,
    approved_by: str,
    expected_amount: float,
    account: str = "checking",
) -> dict:
    """Pay one prepared item. Atomic: either everything changes or nothing does."""
    if not approved_by or not approved_by.strip():
        raise PaymentError("A payment needs the name of the person approving it.")

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        amount, ref_id = _amount_for(conn, kind, target)
        if abs(amount - expected_amount) > 0.005:
            raise PaymentError(
                f"Amount changed since it was prepared (${expected_amount:,.2f} then, "
                f"${amount:,.2f} now). Run the ticket again."
            )

        cash = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if cash is None:
            raise PaymentError(f"No cash account named {account}.")
        if cash["balance"] - amount < 0:
            raise InsufficientFunds(cash["balance"], amount)

        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
        new_balance = round(cash["balance"] - amount, 2)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, today, account),
        )
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
        elif kind == "rent":
            due = conn.execute("SELECT next_due FROM leases WHERE id = ?", (ref_id,)).fetchone()
            conn.execute(
                "UPDATE leases SET next_due = ? WHERE id = ?", (_add_month(due["next_due"]), ref_id)
            )
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today, approved_by.strip()),
        )
        conn.execute("COMMIT")
        return {
            "payment_id": cur.lastrowid,
            "kind": kind,
            "ref_id": ref_id,
            "amount": amount,
            "account": account,
            "paid_at": today,
            "approved_by": approved_by.strip(),
            "balance_before": cash["balance"],
            "balance_after": new_balance,
        }
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def set_ticket_status(ticket_id: int, status: str) -> None:
    if status not in ("open", "resolved"):
        raise ValueError(f"Unknown ticket status {status!r}.")
    conn = _connect()
    try:
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
    finally:
        conn.close()


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_working_copy() -> dict:
    """Copy the original database over the working copy. The original is only read."""
    tmp = DB_PATH.with_suffix(".db.tmp")
    shutil.copyfile(ORIGINAL_DB, tmp)
    os.replace(tmp, DB_PATH)
    original, working = _sha256(ORIGINAL_DB), _sha256(DB_PATH)
    return {
        "working_copy": "data/campus_customs_new.db",
        "copied_from": "data/campus_customs.db",
        "matches_original": original == working,
        "sha256": working,
        "reset_at": datetime.now(timezone.utc).isoformat(),
    }
