"""MCP server for the Campus Customs back office.

Every shop fact an agent uses comes through here. There is no second tools layer
that reaches into the database on its own.

All tools read `data/campus_customs_new.db` over a read-only connection, so no
tool can change stock, prices, or balances. There is deliberately no tool that
sends money: paying rent or an invoice is a human decision, and the agents can
only read what has already been paid.

Tools by table:

  desk          get_shop_date
  tickets       list_open_tickets, list_tickets, get_ticket_detail
  inventory     check_stock
  pricing       get_price_and_margin
  vendors       get_vendor_lead_time
  leases        check_rent_status
  cash_accounts get_cash_balance
  invoices      get_invoice_status, list_open_invoices
  payments      list_payments_made
"""

from fastmcp import FastMCP

from . import db

mcp = FastMCP("campus-customs")


# --- desk -------------------------------------------------------------------

@mcp.tool()
def get_shop_date() -> dict:
    """Get the date the shop is operating on.

    Every due-date and overdue question must be measured against this date, not
    against the real calendar. Agents should call this before judging whether
    anything is late.
    """
    today = db.get_desk_date()
    return {"found": bool(today), "date_today": today}


# --- tickets ----------------------------------------------------------------

@mcp.tool()
def list_open_tickets() -> dict:
    """List every ticket still open on the desk.

    Use this to see what work is waiting. Each ticket carries only the foreign
    keys that match its type, so a rent ticket has a lease_id and no sku.
    """
    rows = db.list_tickets(status="open")
    return {"found": bool(rows), "count": len(rows), "tickets": rows}


@mcp.tool()
def list_tickets() -> dict:
    """List every ticket, open or resolved, with its status.

    The dashboard uses this to show which tickets are done. Agents work from
    list_open_tickets instead.
    """
    rows = db.list_tickets()
    return {"found": bool(rows), "count": len(rows), "tickets": rows}


@mcp.tool()
def get_ticket_detail(ticket_id: int) -> dict:
    """Get one ticket by id, including any sku, lease, or invoice it points at.

    Args:
        ticket_id: The ticket number, e.g. 101.
    """
    row = db.get_ticket(ticket_id)
    if row is None:
        return {"found": False, "ticket_id": ticket_id,
                "message": f"No ticket with id {ticket_id}."}
    return {"found": True, **row}


# --- inventory --------------------------------------------------------------

@mcp.tool()
def check_stock(sku: str, size: str) -> dict:
    """Check how many units of a product are in stock in one size.

    Inventory is keyed on (sku, size), so a size is required. If the size asked
    for is short, the other sizes on record come back too.

    Args:
        sku: Product code, e.g. "CC-TEE-WHITE".
        size: "S", "M", "L", "XL", or "OS" for one-size items.
    """
    row = db.get_stock(sku, size)
    if row is None:
        return {
            "found": False,
            "sku": sku,
            "size": size,
            "message": f"No inventory record for {sku} in size {size}.",
        }

    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "qty": row["qty"],
        "location": row["location"],
        "in_stock": row["qty"] > 0,
        "other_sizes": [s for s in db.get_sizes_for_sku(sku) if s["size"] != size],
    }


# --- leases -----------------------------------------------------------------

@mcp.tool()
def check_rent_status(lease_id: int, account: str = "checking") -> dict:
    """Look up a lease, when its rent is next due, and whether cash covers it.

    Days are counted from the desk date, not the real date, so results don't
    drift. A negative value in days_until_due means the payment is late.

    This tool does not pay anything. Sending rent is a human decision.

    Args:
        lease_id: Which lease to check.
        account: Cash account to measure against. Defaults to "checking".
    """
    lease = db.get_lease(lease_id)
    if lease is None:
        return {
            "found": False,
            "lease_id": lease_id,
            "message": f"No lease with id {lease_id}.",
        }

    today = db.get_desk_date()
    cash = db.get_cash_account(account)
    rent = lease["monthly_rent"]
    balance = cash["balance"] if cash else None
    days = db.days_between(today, lease["next_due"])

    return {
        "found": True,
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": rent,
        "next_due": lease["next_due"],
        "as_of": today,
        "days_until_due": days,
        "is_overdue": days is not None and days < 0,
        "account": account,
        "balance": balance,
        "covers_rent": None if balance is None else balance >= rent,
        "balance_after_rent": None if balance is None else round(balance - rent, 2),
    }


# --- pricing ----------------------------------------------------------------

@mcp.tool()
def get_price_and_margin(sku: str, qty: int = 1, discount_pct: float = 0.0) -> dict:
    """Get cost and list price for a product, and test a proposed discount.

    Used to answer bulk discount requests. A discount that prices the item below
    unit cost comes back with below_cost set to True.

    Args:
        sku: Product code, e.g. "CC-HOOD-NAVY".
        qty: How many units the customer wants. Defaults to 1.
        discount_pct: Discount to test, as a percentage off list. 0 means none.
    """
    row = db.get_pricing(sku)
    if row is None:
        return {
            "found": False,
            "sku": sku,
            "message": f"No pricing record for {sku}.",
        }

    cost = row["unit_cost"]
    list_price = row["list_price"]
    discounted = round(list_price * (1 - discount_pct / 100), 2)

    return {
        "found": True,
        "sku": row["sku"],
        "unit_cost": cost,
        "list_price": list_price,
        "margin_per_unit": round(list_price - cost, 2),
        "qty": qty,
        "discount_pct": discount_pct,
        "discounted_unit_price": discounted,
        "below_cost": discounted < cost,
        "max_discount_pct": round((1 - cost / list_price) * 100, 2),
        "total_at_discount": round(discounted * qty, 2),
        "total_margin_at_discount": round((discounted - cost) * qty, 2),
    }


# --- vendors ----------------------------------------------------------------

@mcp.tool()
def get_vendor_lead_time(vendor_id: int) -> dict:
    """Get a vendor's details and how many days they take to deliver.

    Use lead_days to work out the earliest a reorder could arrive. Count the
    days from the shop date, not the real date.

    Args:
        vendor_id: The vendor id, e.g. 1 for Bulldog Print Co.
    """
    row = db.get_vendor(vendor_id)
    if row is None:
        return {"found": False, "vendor_id": vendor_id,
                "message": f"No vendor with id {vendor_id}."}
    return {"found": True, "as_of": db.get_desk_date(), **row}


# --- cash_accounts ----------------------------------------------------------

@mcp.tool()
def get_cash_balance(account: str = "checking") -> dict:
    """Get the balance of a cash account.

    This is the hard ceiling on anything the shop spends. It is read-only: no
    agent can move money.

    Args:
        account: Account name. Defaults to "checking".
    """
    row = db.get_cash_account(account)
    if row is None:
        return {"found": False, "account": account,
                "message": f"No cash account named {account}."}
    return {"found": True, **row}


# --- invoices ---------------------------------------------------------------

@mcp.tool()
def get_invoice_status(invoice_id: int) -> dict:
    """Check one invoice: amount, due date, whether it is still unpaid, and
    whether it is overdue as of the shop date.

    An invoice with status "open" has not been paid. Orders that depend on an
    unpaid invoice must not be promised as shipping.

    Args:
        invoice_id: The invoice number, e.g. 501.
    """
    row = db.get_invoice(invoice_id)
    if row is None:
        return {"found": False, "invoice_id": invoice_id,
                "message": f"No invoice with id {invoice_id}."}

    today = db.get_desk_date()
    days = db.days_between(today, row["due_date"])
    vendor = db.get_vendor(row["vendor_id"])

    return {
        "found": True,
        **row,
        "vendor_name": vendor["name"] if vendor else None,
        "vendor_lead_days": vendor["lead_days"] if vendor else None,
        "as_of": today,
        "is_paid": row["status"].lower() != "open",
        "days_until_due": days,
        "is_overdue": row["status"].lower() == "open" and days is not None and days < 0,
        "days_overdue": abs(days) if days is not None and days < 0 else 0,
    }


@mcp.tool()
def list_open_invoices() -> dict:
    """List every unpaid invoice, with how overdue each one is.

    Use this to see what the shop owes before judging whether it can afford
    anything else.
    """
    today = db.get_desk_date()
    rows = []
    for inv in db.list_invoices(status="open"):
        days = db.days_between(today, inv["due_date"])
        rows.append({
            **inv,
            "days_until_due": days,
            "is_overdue": days is not None and days < 0,
        })
    return {
        "found": bool(rows),
        "as_of": today,
        "count": len(rows),
        "total_owed": round(sum(r["amount"] for r in rows), 2),
        "invoices": rows,
    }


# --- payments ---------------------------------------------------------------

@mcp.tool()
def list_payments_made() -> dict:
    """List payments the shop has already sent, including who approved each one.

    Read-only on purpose. There is no tool that sends a payment: rent and
    invoices are paid by a human, and an agent can only recommend it.
    """
    rows = db.list_payments()
    return {
        "found": bool(rows),
        "count": len(rows),
        "payments": rows,
        "note": "Agents cannot send payments. A human approves and records them.",
    }


if __name__ == "__main__":
    mcp.run()
