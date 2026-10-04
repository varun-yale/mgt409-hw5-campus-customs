# Campus Customs — Operations Harness

Notes on the Campus Customs database. Starting with what's in each table, will
add more as I build out the agent system.

Original database: `data/campus_customs.db`
Working copy: `data/campus_customs_new.db`

I made the copy so I can change things without touching the original. Everything
from here should read and write to the copy.

---

## 1. The tables

There are nine. Three cover products (`inventory`, `pricing`, `vendors`), four
cover money (`leases`, `cash_accounts`, `invoices`, `payments`), `tickets` is the
request queue, and `desk` holds the date.

### desk

| Field | What it is |
|---|---|
| `date_today` | The current date. Right now it's `2026-08-31`. |
| `notes` | Free text. Empty at the moment. |

Only one row. This is the date the system runs on instead of the real clock, so
anything about due dates or overdue bills needs to be checked against this.

### tickets

| Field | What it is |
|---|---|
| `id` | Ticket number. |
| `type` | `customer_order`, `rent_notice`, or `price_override`. |
| `requester` | Who sent it in. |
| `subject` | Short description. |
| `sku`, `size`, `qty` | Product info, if the ticket is about an item. Null if not. |
| `lease_id` | Points to `leases`, used on rent tickets. |
| `invoice_id` | Points to `invoices` when there's a bill involved. |
| `status` | `open` or closed. All three right now are open. |
| `notes` | Whatever the requester said. |
| `created_at` | Timestamp with timezone. |

This is the inbox. A lot of the columns are nullable because each ticket only
fills in the ones that apply to its type. Rent tickets have a `lease_id` and no
`sku`, product tickets are the other way around.

### inventory

| Field | What it is |
|---|---|
| `sku` | Product code. |
| `name` | Product name. |
| `size` | `S`, `M`, `L`, `XL`, or `OS` for one-size items. |
| `qty` | How many are in stock. |
| `location` | Which aisle. |

The primary key is `(sku, size)`, so there's a separate row per size. Checking
stock without specifying a size won't give a useful answer.

### pricing

| Field | What it is |
|---|---|
| `sku` | Product code. |
| `unit_cost` | What the shop pays. |
| `list_price` | What it sells for. |

Keyed on `sku` only, no size. So price is the same across sizes even though
stock isn't. Useful for working out margin on the discount ticket.

### vendors

| Field | What it is |
|---|---|
| `id` | Vendor ID. |
| `name` | Vendor name. |
| `specialty` | What they supply. |
| `lead_days` | Days between ordering and delivery. |

`lead_days` matters for any restocking question since it sets how long a reorder
actually takes.

### leases

| Field | What it is |
|---|---|
| `id` | Lease ID. |
| `space_name` | The space being rented. |
| `landlord` | Who gets paid. |
| `monthly_rent` | Rent per month. |
| `next_due` | When the next payment is due. |
| `notes` | Free text. |

Holds the recurring rent the shop owes. Ticket 102 links here, and `next_due` is
where any "when is rent due" question gets answered.

### cash_accounts

| Field | What it is |
|---|---|
| `name` | Account name. |
| `balance` | Current balance. |
| `date` | When that balance was accurate. |

One account, `checking`. This is the limit on anything that involves spending.

### invoices

| Field | What it is |
|---|---|
| `id` | Invoice number. |
| `vendor_id` | Links to `vendors.id`. |
| `amount` | Amount owed. |
| `due_date` | When it's due. |
| `status` | `open` or paid. |
| `description` | What it's for. |

Tracks what the shop owes vendors. Agents need it to see which bills are still
open and which are past their `due_date`, like invoice 501 on ticket 101.

### payments

| Field | What it is |
|---|---|
| `id` | Payment ID. |
| `kind` | What kind of payment (rent, invoice, etc). |
| `ref_id` | Which lease or invoice it covers. |
| `amount` | Amount paid. |
| `account` | Which account it came out of. |
| `paid_at` | Timestamp. |
| `approved_by` | Who approved it. |

Empty right now, nothing has been paid yet. `ref_id` has no foreign key on it
because what it points to depends on `kind`. `approved_by` is there so every
payment has a record of who signed off.

---

## 2. The three open tickets

All three are still open as of `2026-08-31`. Each one pulls from different
tables, and all three have a problem.

### Ticket 101, customer order from Tauhid Zaman

Wants one `CC-TEE-WHITE` in size S. Has `invoice_id` 501 attached.

Tables involved: `inventory`, `pricing`, `invoices`, `vendors`.

Problem: that size is at `qty = 0`, so it can't be filled from stock. Invoice 501
is a rush reprint for the same SKU and size ($840, from Bulldog Print Co), so a
restock is already ordered. But invoice 501 is still `open` and its due date was
`2026-08-28`, which is three days before the current date, so it's overdue and
unpaid. Bulldog Print Co has `lead_days` of 5.

So the order is stuck behind an unpaid bill, and even once that's paid there's
another five days of lead time.

### Ticket 102, rent notice from Elm City Properties

Has `lease_id` 1. Note says rent is due in two days.

Tables involved: `leases`, `cash_accounts`, and `payments` once something is paid.

Lease 1 is the Chapel Street shop, $2,400 a month, `next_due` of `2026-09-02`.
That's two days after `2026-08-31`, so the note is right.

Problem: checking only has $3,400. Rent ($2,400) plus the overdue invoice ($840)
is $3,240, which leaves $160. Both can technically be paid but it's tight, and
tickets 101 and 102 are drawing on the same account.

### Ticket 103, price override from Yale AI Club

Wants 20 `CC-HOOD-NAVY` hoodies in size M with a bulk discount.

Tables involved: `inventory`, `pricing`.

Two problems here. Stock-wise, size M only has 8, so that's 12 short. Other sizes
have more but the request is specifically for M. Price-wise, unit cost is $22 and
list is $58, so there's $36 of margin per hoodie. A discount is possible but it
can't go below cost.

---

## 3. Things to remember

1. Dates come from `desk.date_today`, not the real date. Invoice 501 only shows
   up as overdue when compared against `2026-08-31`.
2. Tickets 101 and 102 both need money from the same $3,400 account, so they
   can't be handled separately.
3. Stock is tracked per size. Both product tickets run into size-specific
   shortages that a check on SKU alone would miss.

---

## 4. MCP tools

The MCP server lives in `mcp_server/` and reads `data/campus_customs_new.db` in
read-only mode. Three tools, one built around each open ticket.

### `check_stock(sku, size)`

**Table it reads:** `inventory`
**Ticket it unlocks:** 101

Ticket 101 wants one `CC-TEE-WHITE` in size S, and `inventory` is keyed on
`(sku, size)`, so this tool is the only way to find out that size S is sitting at
`qty = 0` while M, L, and XL still have stock, which is the fact that turns the
ticket from a normal order into a restock problem.

Returns on that call: `qty 0`, `in_stock false`, and the other three sizes with
5, 3, and 2 units.

### `check_rent_status(lease_id, account="checking")`

**Table it reads:** `leases` (also pulls `cash_accounts` and `desk`)
**Ticket it unlocks:** 102

Ticket 102 is just an email saying rent is due in two days, so this tool is the
right one because it replaces that claim with lease 1's actual $2,400 and
`2026-09-02` due date, counts the days from `desk.date_today` instead of the real
clock, and checks the amount against the $3,400 in checking, which is what
exposes that rent and invoice 501 are competing for the same account.

Returns on that call: `days_until_due 2`, `covers_rent true`,
`balance_after_rent 1000.0`.

### `get_price_and_margin(sku, qty=1, discount_pct=0)`

**Table it reads:** `pricing`
**Ticket it unlocks:** 103

Ticket 103 asks for a bulk discount without naming a number, so this tool is the
right one because it pulls the $22 unit cost against the $58 list price and works
out the 62.07% ceiling where the hoodies would start selling at a loss, which
gives a floor to negotiate against instead of guessing at a discount.

Returns on a 20-unit, 15% test: `discounted_unit_price 49.3`, `below_cost false`,
`total_margin_at_discount 546.0`.

### Tools added for the agent team

Problem 5 added eight more so each of the five agents can get at the part of the
shop it owns. Full list, with the table behind each one:

| Tool | Table it reads | What it's for |
|---|---|---|
| `get_shop_date` | `desk` | The date everything is measured from. |
| `list_open_tickets` | `tickets` | What work is waiting on the desk. |
| `get_ticket_detail` | `tickets` | One ticket, with its sku/lease/invoice links. |
| `check_stock` | `inventory` | Units on hand for one sku in one size. |
| `get_price_and_margin` | `pricing` | Cost, list, and whether a discount goes below cost. |
| `get_vendor_lead_time` | `vendors` | How many days a vendor takes to deliver. |
| `check_rent_status` | `leases` | Rent amount, due date, and whether cash covers it. |
| `get_cash_balance` | `cash_accounts` | What the shop has to spend. |
| `get_invoice_status` | `invoices` | One bill: amount, paid or not, how overdue. |
| `list_open_invoices` | `invoices` | Everything still owed, with a total. |
| `list_payments_made` | `payments` | What has actually been paid, and who approved it. |
| `list_tickets` | `tickets` | Every ticket, open or resolved. Added in Problem 7 for the dashboard; no agent has it. |

Twelve tools over all nine tables.

### Notes

None of them write anything. The connection opens read-only, so a write raises
an error rather than changing shop data. If a sku, lease, or size isn't in the
database the tool returns `found: False` with a message instead of making up a
number.

There is deliberately no tool that sends a payment. `list_payments_made` can read
what has already gone out, but nothing on this server can move money. Money only
moves through the backend's approve route (section 7).

---

## 5. The agent team

Five PydanticAI agents in `backend/`, each with its own prompt in
`backend/prompts/`. All five run on `gpt-6-luna` through Portkey, and all shop
facts come from the MCP server above over `.mcp.json`. No agent queries the
database directly.

How the model is reached (`build_model()` in `backend/agents.py`):

- **Gateway:** `https://api.portkey.ai/v1`, using the OpenAI **Responses API**
  (`/v1/responses`). gpt-6-luna only accepts function tools alongside reasoning
  there; on `/v1/chat/completions` it rejects them.
- **Auth and routing:** `PORTKEY_API_KEY` is sent as `x-portkey-api-key`, and
  `PORTKEY_PROVIDER` (`@openai-personal`) as `x-portkey-provider`, so Portkey
  uses the OpenAI key stored in that integration. Both come from `HW5/.env`,
  which overrides anything exported in the shell. The Portkey key is never put
  in the `Authorization` header, so it can't reach OpenAI.
- **No fallback.** If either setting is missing, the backend refuses to start a
  run rather than trying another model.

| Agent | Prompt | What it owns | MCP tools it can use |
|---|---|---|---|
| **Boss** | `boss.md` | Routes each ticket to the right specialists, then makes the final call and flags what a human has to approve. | `get_shop_date`, `list_open_tickets`, `get_ticket_detail` |
| **Inventory** | `inventory.md` | Stock by sku and size, how short an order is, what a reorder would take. | `get_shop_date`, `get_ticket_detail`, `check_stock`, `get_vendor_lead_time`, `get_invoice_status` |
| **Accounting** | `accounting.md` | What the shop owes, what it can afford, and whether a discount clears cost. | `get_shop_date`, `get_ticket_detail`, `get_invoice_status`, `list_open_invoices`, `get_cash_balance`, `get_price_and_margin`, `list_payments_made` |
| **Facilities** | `facilities.md` | Leases and rent, including whether the balance after rent is thin. | `get_shop_date`, `get_ticket_detail`, `check_rent_status`, `get_cash_balance`, `list_open_invoices` |
| **Customer Service** | `customer_service.md` | What the customer actually gets told, and what can't be promised. | `get_shop_date`, `list_open_tickets`, `get_ticket_detail`, `check_stock`, `get_invoice_status` |

Each agent only sees the tools its job needs. Customer Service can't read the
cash balance, Facilities can't price hoodies. Narrower tool lists mean a smaller
schema in every request, which costs fewer tokens as well.

### How a ticket moves

1. Boss reads the ticket and picks which specialists should see it.
2. Those specialists each pull their own facts from MCP and report back with a
   recommendation, any blockers, and whether a human needs to sign off.
3. Boss reads the reports and makes one decision, marking anything that spends
   money as needing approval.

### Delegation: every agent can reach every other

On top of that flow, all five agents carry one extra tool, `ask_colleague(colleague,
question)`, defined in `backend/agents.py`. Any agent can hand a question to any
of the other four, so the team is fully connected rather than a strict hub around
the Boss. The colleague runs as itself, with its own prompt and its own MCP tools,
and its answer goes back to whoever asked. For example, Facilities can ask
Accounting what else is due out of checking before it calls the balance after
rent safe, and Customer Service can ask Inventory for the restock time before it
words a reply.

`ask_colleague` is not a shop-data tool. It never touches the database, it only
runs another agent, and that agent still gets its facts from MCP.

Three caps keep delegation from looping:

- A chain of asks stops two hops deep (`MAX_DELEGATION_DEPTH = 2`).
- Nobody already in the chain can be asked again, so A → B → A is refused.
- Each ticket gets 6 asks in total across the whole team (`DELEGATIONS_PER_TICKET`).

When a cap is hit, the tool tells the agent to answer with what it has.

### The audit trail

Every step appends to `output/audit_trail.json` as it happens: the Boss's
routing, each specialist report, every delegation (logged as
`delegated_by_<agent>` under the agent that answered), and the Boss's final call.
Each step records the agent, ticket, action, model, a short prompt summary, the
MCP tools called with their arguments, truncated tool results, the output,
whether it needs human approval, tokens in and out, duration, and any error.

The file keeps a list of runs. A new run is added after the old ones and never
replaces them. Failed calls are logged with their error too, so a run that dies
partway through still leaves a record.

---

## 6. Safety

What a real shop would want in place before letting agents near real customers
and real money.

### Guardrails that are built in

**Agents cannot spend money.** There is no tool that sends a payment, pays an
invoice, or settles rent. The furthest any agent can go is to prepare a payment
in the Boss's `proposed_payments` and set `needs_human_approval`. The amount
isn't the agent's to set; the backend looks it up. A person decides and a person's name lands in
`payments.approved_by`. This is the single most important control here, because
it means the worst case for a confused agent is bad advice rather than a drained
account.

**The database is read-only.** The MCP connection opens with `mode=ro`, so a bug
or a prompt injection can't change stock, prices, or balances. A write attempt
raises an error instead. The only writes are the backend's approve and reset
routes, through `mcp_server/ledger.py`, which is not an MCP tool.

**Agents can't reach the database directly.** Every fact goes through the MCP
server, so there's one place where access is defined and one place to audit. No
agent holds a connection string.

**Least privilege per agent.** Each role is filtered down to the tools its job
needs, so Customer Service literally cannot read the cash balance.

**No invented facts.** Tools return `found: false` rather than a plausible
number, and the prompts tell each agent to say when a fact is missing and set
`confident` to false instead of filling the gap.

**Dates come from the shop.** Everything about overdue and due-soon is measured
from `desk.date_today`, so the same run gives the same answer tomorrow.

**Nothing gets promised against an unpaid bill.** All four specialist prompts
carry the rule that an order waiting on an open invoice is not shipping, so no
agent can give a customer a date that assumes somebody pays a bill today.

**Everything is logged.** `output/audit_trail.json` records each step: which
agent, which tools, what came back, what it decided, tokens, and duration.
Delegations are logged with who asked whom, and old runs are never overwritten.

**Delegation can't spread a decision around.** Agents can ask each other
questions, but asking a colleague doesn't give anyone new powers. The colleague
still has only its own tools, and no chain of asks ends at a tool that pays.

### Limits that keep token use down

- `UsageLimits(request_limit=6, tool_calls_limit=10)` on every agent run, so a
  model that gets stuck in a loop stops instead of billing forever.
- Tool access is filtered per agent, so each request carries only that agent's
  MCP tools instead of every tool on the server: 3 for the Boss, 5 each for Inventory,
  Facilities, and Customer Service, and 7 for Accounting. On top of that, every
  agent carries `ask_colleague`, except the Boss during its routing step.
- Typed outputs, so specialists return a short structured report rather than
  paragraphs the Boss then has to re-read.
- Audit entries truncate long tool results instead of storing whole payloads.
- The Boss gets a condensed bundle of specialist summaries, not full transcripts.
- Delegation is capped at two hops, no repeat agents in a chain, and 6 asks per
  ticket, so agents can't keep passing a question around.
- If the model provider returns a quota or billing error, the run stops right
  away instead of failing the same call for every remaining ticket.

### What's still missing for a real shop

Worth being honest about. This would need before going live: login on the
backend so only the owner can approve (right now anyone who can reach port 8000
can approve under any name), rate limits per customer, PII handling for customer
names in the audit log, an escalation path when an agent is not confident, and
alerting when the trail shows repeated errors.

---

## 7. Backend routes

`backend/main.py` is a FastAPI app for the dashboard. Start it from `backend/`
with `uvicorn main:app --reload --port 8000`.

| Route | What it does |
|---|---|
| `GET /health` | Confirms the backend is up and which model the agents use. |
| `GET /tickets` | All three tickets, each marked open or resolved, with how many payments are waiting for approval. |
| `POST /tickets/{id}/run` | Runs the five-agent team on one open ticket and prepares any payments the Boss proposes. Moves no money. |
| `GET /events` | Recent agent steps from the audit trail, newest first: who acted, what they said, and which tools they used. Takes `limit`, `ticket_id`, and `since` (so the dashboard can follow one live run). |
| `GET /approvals` | Payments the agents prepared, pending or approved. Takes `status`. |
| `POST /approvals/{id}/approve` | A person approves one prepared payment. The only route that changes cash. Needs `approved_by`. |
| `GET /cash` | Current checking balance, plus the total waiting for approval. |
| `POST /reset` | Copies the original database over `campus_customs_new.db` and clears prepared payments for a fresh run. |

How the pieces fit:

- **Reads go through MCP.** Tickets, cash, and the amounts behind a prepared
  payment all come from the MCP server, the same way the agents get them.
  `list_tickets` was added for the dashboard because `list_open_tickets` hides
  resolved tickets.
- **Preparing isn't paying.** The Boss lists payments in `proposed_payments`
  with no dollar amounts. The backend prices each one from the database
  (invoice amount, lease rent, or unit cost × qty for a purchase) and stores it
  in `output/approvals.json`. Proposals that don't match the database are
  skipped, and a payment that's already pending isn't prepared twice.
- **Approval is strict.** The approve route re-reads the amount and the balance
  in one transaction, refuses anything that would take checking below zero, and
  then updates cash, marks the invoice paid or moves rent to next month, and
  writes a `payments` row with the approver's name. If anything fails, nothing
  changes.
- **Resolved** means the team made its decision and no payment for that ticket
  is still waiting. A resolved ticket can't be run again until a reset.
- **One run at a time.** Each run appends to the audit trail, and two runs
  overlapping could overwrite each other's entries.
- **Quota errors are clean.** If Portkey refuses (402/412/429), the run route
  returns 503 `portkey_quota_exhausted`, the error is in the audit trail, and no
  other model is tried.
- **Reset keeps history.** It restores shop data and clears prepared payments
  but leaves `audit_trail.json` alone. The original database is only read.

---

## 8. Dashboard

`frontend/` is a React + Vite + TypeScript app that calls the backend at
`http://localhost:8000` (CORS allows `http://localhost:5173`). Start the
backend first, then run `npm run dev` from `frontend/` and open
`http://localhost:5173`. Adding `?ticket=101` opens that ticket directly.

- **Tickets** on the left, each marked Open, Running, or Resolved, with a note
  when a payment is waiting.
- **The team, Activity, and Run summary** in the middle. All five agents are
  shown, and the ones not called are dimmed. During a run the page polls
  `GET /events?since=…`, so each step shows up as it's written: who acted, what
  they said, which MCP tools they used, and who asked whom.
- **Checking and the approval queue** on the right, always in view. Approving
  needs a name, a payment bigger than the balance is blocked, and the balance
  refreshes after each approval.
- **Errors** are shown as banners, not crashes: a Portkey quota error says so
  and confirms no other model was tried, and a stopped backend shows Retry.
- Every run is tagged with its model. Anything other than gpt-6-luna is shown
  in amber, so a test run can't pass for a graded one.

Design notes are in `output/design.md`.

---

## 9. What the real runs showed

The three tickets were resolved by real gpt-6-luna runs, appended to
`output/audit_trail.json` (`run-bddd17ca`, `run-c0f316a0`, `run-fdd1717a`).
Full results are in `output/resolved_tickets.json` and the Actual sections of
`output/desk_tickets.html`. A few things the safety rules did in practice:

- **Human approval held.** Agents prepared two payments (invoice 501 for $840
  and rent for $2,400). Neither moved until Varun Matta approved it in the
  dashboard. Checking went $3,400 → $2,560 → $160 and never below zero.
- **The loop guard fired.** On 102, Accounting tried to ask Facilities back
  while answering Facilities, and `ask_colleague` refused it.
- **Depth and request limits fired.** On 103, a third-hop ask was refused,
  and the Boss hit its 6-request cap while answering Customer Service. Customer
  Service marked itself not confident instead of guessing, and the Boss still
  made the final call.
- **No payment, no approval.** On 103 the Boss proposed no payment (it wanted
  the club's discount figure first), so the ticket resolved with cash
  unchanged.
