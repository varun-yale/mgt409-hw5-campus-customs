# Campus Customs MCP Server

## What it's for

This is an MCP server that gives an agent read access to the Campus Customs back
office. Instead of guessing at stock levels or prices, the agent calls a tool and
gets the real row out of the database.

Right now there are three open tickets on the desk, and the three tools here are
each built to answer the question one of those tickets is stuck on.

## Database

Everything reads `data/campus_customs_new.db`, the working copy made in Problem 2.
The original `campus_customs.db` is left alone.

The connection opens in read-only mode, so none of these tools can change stock,
prices, or balances even by accident. Writes come later.

If a row isn't in the database, the tool returns `found: False` with a short
message. It never fills in a number that isn't there.

## The three tools

### `check_stock(sku, size)`

Reads `inventory`. Returns the quantity on hand for one product in one size, plus
the aisle it's in. Inventory is keyed on `(sku, size)`, so the size argument is
required. If the requested size is short, the other sizes for that sku come back
as well.

### `check_rent_status(lease_id, account="checking")`

Reads `leases`, and also pulls `cash_accounts` and `desk` to answer the follow-up
question of whether the money is actually there. Returns the rent amount, the due
date, how many days away that is, and what the balance looks like after paying.
Day counts are measured from `desk.date_today`, not the real date, so the answer
doesn't change depending on when you run it. A negative `days_until_due` means
the payment is already late.

### `get_price_and_margin(sku, qty=1, discount_pct=0)`

Reads `pricing`. Returns unit cost, list price, and the margin between them. If
you pass a `discount_pct` it prices out that discount for the requested quantity
and flags `below_cost` when the discount would sell the item at a loss. Also
returns `max_discount_pct`, the largest discount that still breaks even.

## The rest of the tools

Problem 5 added eight more so the five agents can each reach their own part of
the shop. Every table is covered now.

| Tool | Table | What it does |
|---|---|---|
| `get_shop_date()` | `desk` | Returns the date the shop runs on. Call it before judging anything late. |
| `list_open_tickets()` | `tickets` | Every ticket still open, with its linked ids. |
| `get_ticket_detail(ticket_id)` | `tickets` | One ticket by number. |
| `get_vendor_lead_time(vendor_id)` | `vendors` | Vendor details and delivery days. |
| `get_cash_balance(account)` | `cash_accounts` | Balance on an account. Read-only. |
| `get_invoice_status(invoice_id)` | `invoices` | One bill, whether it's paid, and how overdue as of the shop date. |
| `list_open_invoices()` | `invoices` | Everything unpaid, with a running total. |
| `list_payments_made()` | `payments` | What has already been sent and who approved it. |
| `list_tickets()` | `tickets` | Every ticket, open or resolved. Added in Problem 7 for the dashboard; no agent has it. |

Twelve tools over nine tables.

## What this server will not do

There is no tool that sends a payment, places an order, or writes anything at
all. That's deliberate, not an oversight. Rent and invoices get paid by a person,
and the agents can only recommend it — the worst a confused agent can do here is
give bad advice.

The backend's approve and reset routes do write, through `ledger.py`. That file
isn't registered as a tool, so no agent can call it.

## Files

```
mcp_server/
  server.py    FastMCP instance and the twelve tool definitions
  db.py        read-only SQLite helpers, all the actual queries
  ledger.py    human-only writes for the backend (approve a payment, reset); not a tool
  README.md    this file
```

## Running it

You don't start this server by hand. The backend and the agents launch it over
stdio using `.mcp.json` at the project root, which points at
`python -m mcp_server.server` in this folder. Instead of absolute paths, it uses
`${HW5_PYTHON}` and `${HW5_ROOT}`, which `backend/agents.py` sets to the running
interpreter and the project folder, so it works wherever the repo is cloned.

The Problem 4 check of each tool against the database is saved in
`output/mcp_smoke.json`.
