"""FastAPI backend for the Campus Customs dashboard.

Run from the backend/ folder:

    uvicorn main:app --reload --port 8000

Shop facts come from the MCP server, the same way the agents get them. The only
writes are the two things a person does: approving a prepared payment and
resetting the working database. Those go through `mcp_server/ledger.py`, which
is not an MCP tool, so no agent can call it.

Agents never pay anything. When the Boss's decision includes a payment, this
backend prepares it as a pending approval, with the amount looked up from the
database. It only moves money when someone calls the approve route, and it
refuses any payment that would take checking below zero.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parent
for p in (BACKEND_DIR, ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastmcp import Client  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import audit  # noqa: E402
from agents import active_model_name, build_router, build_team, mcp_config, mcp_toolsets  # noqa: E402
from mcp_server import ledger  # noqa: E402
from models import AgentName, BossDecision, PaymentKind, ProposedPayment  # noqa: E402
from run_team import QuotaExhausted, run_ticket, summarize  # noqa: E402

MCP_CONFIG = mcp_config()
APPROVALS_PATH = Path(os.getenv("APPROVALS_PATH") or ROOT / "output" / "approvals.json")

app = FastAPI(title="Campus Customs backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_approvals_lock = asyncio.Lock()
_running: set[int] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- MCP ----------------------------------------------------------------------

async def mcp_calls(*calls: tuple[str, dict]) -> list[dict]:
    """Call one or more MCP tools over a single connection."""
    out = []
    async with Client(MCP_CONFIG) as client:
        for tool, args in calls:
            res = await client.call_tool(tool, args)
            out.append(res.structured_content or json.loads(res.content[0].text))
    return out


async def mcp_call(tool: str, args: dict | None = None) -> dict:
    return (await mcp_calls((tool, args or {})))[0]


# --- prepared payments ----------------------------------------------------------

def _load_approvals() -> list[dict]:
    if not APPROVALS_PATH.exists() or not APPROVALS_PATH.read_text().strip():
        return []
    return json.loads(APPROVALS_PATH.read_text())["approvals"]


def _save_approvals(items: list[dict]) -> None:
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPROVALS_PATH.write_text(json.dumps({"approvals": items}, indent=2) + "\n")


def _pending_for(items: list[dict], ticket_id: int) -> list[dict]:
    return [a for a in items if a["ticket_id"] == ticket_id and a["status"] == "pending"]


async def quote(p: ProposedPayment) -> dict:
    """Turn a proposal into a priced item using MCP. Raises ValueError if it can't."""
    if p.kind is PaymentKind.INVOICE:
        if p.invoice_id is None:
            raise ValueError("An invoice payment needs an invoice_id.")
        inv = await mcp_call("get_invoice_status", {"invoice_id": p.invoice_id})
        if not inv["found"]:
            raise ValueError(inv["message"])
        if inv["is_paid"]:
            raise ValueError(f"Invoice {inv['id']} is already paid.")
        return {
            "kind": "invoice",
            "target": {"invoice_id": inv["id"]},
            "amount": inv["amount"],
            "payee": inv["vendor_name"],
            "description": f"Invoice {inv['id']}: {inv['description']}",
        }

    if p.kind is PaymentKind.RENT:
        if p.lease_id is None:
            raise ValueError("A rent payment needs a lease_id.")
        lease = await mcp_call("check_rent_status", {"lease_id": p.lease_id})
        if not lease["found"]:
            raise ValueError(lease["message"])
        return {
            "kind": "rent",
            "target": {"lease_id": lease["lease_id"]},
            "amount": lease["monthly_rent"],
            "payee": lease["landlord"],
            "description": f"Rent for {lease['space_name']}, due {lease['next_due']}",
        }

    # purchase
    if not (p.sku and p.size and p.qty and p.qty > 0 and p.vendor_id is not None):
        raise ValueError("A purchase needs sku, size, a positive qty, and vendor_id.")
    stock, price, vendor = await mcp_calls(
        ("check_stock", {"sku": p.sku, "size": p.size}),
        ("get_price_and_margin", {"sku": p.sku, "qty": p.qty}),
        ("get_vendor_lead_time", {"vendor_id": p.vendor_id}),
    )
    for r in (stock, price, vendor):
        if not r["found"]:
            raise ValueError(r["message"])
    return {
        "kind": "purchase",
        "target": {"sku": p.sku, "size": p.size, "qty": p.qty, "vendor_id": p.vendor_id},
        "amount": round(price["unit_cost"] * p.qty, 2),
        "payee": vendor["name"],
        "description": (
            f"Restock {p.qty} x {stock['name']} size {p.size} at "
            f"${price['unit_cost']:.2f} unit cost, {vendor['lead_days']} lead days"
        ),
    }


async def prepare_approvals(
    decision: BossDecision, ticket_id: int, run_id: str
) -> tuple[list[dict], list[dict]]:
    """Store the Boss's proposed payments as pending approvals. Pays nothing."""
    prepared, skipped = [], []
    async with _approvals_lock:
        items = _load_approvals()
        for p in decision.proposed_payments:
            proposal = p.model_dump(mode="json")
            try:
                q = await quote(p)
            except ValueError as exc:
                skipped.append({"proposal": proposal, "reason": str(exc)})
                continue
            dup = next(
                (a for a in items if a["status"] == "pending"
                 and a["kind"] == q["kind"] and a["target"] == q["target"]),
                None,
            )
            if dup:
                skipped.append({"proposal": proposal, "reason": f"Already prepared as {dup['id']}."})
                continue
            rec = {
                "id": f"apr-{uuid.uuid4().hex[:8]}",
                "ticket_id": ticket_id,
                **q,
                "reason": p.reason,
                "status": "pending",
                "prepared_by": AgentName.BOSS.value,
                "prepared_at": _now(),
                "run_id": run_id,
                "approved_by": None,
                "approved_at": None,
                "payment": None,
            }
            items.append(rec)
            prepared.append(rec)
        _save_approvals(items)
    return prepared, skipped


# --- routes -----------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": active_model_name()}


@app.get("/tickets")
async def list_tickets() -> dict:
    """Every ticket with open/resolved status and how many approvals are waiting."""
    data = await mcp_call("list_tickets")
    approvals = _load_approvals()
    tickets = [
        {
            "id": t["id"],
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "notes": t["notes"],
            "status": t["status"],
            "resolved": t["status"] == "resolved",
            "pending_approvals": len(_pending_for(approvals, t["id"])),
        }
        for t in data["tickets"]
    ]
    return {"count": len(tickets), "tickets": tickets}


@app.post("/tickets/{ticket_id}/run")
async def run_ticket_route(ticket_id: int) -> dict:
    """Run the five-agent team on one ticket and prepare any payments it proposes."""
    # One team run at a time. Each run's AuditTrail appends to the history it
    # loaded at start, so two overlapping runs could drop each other's entries.
    if _running:
        raise HTTPException(409, f"Ticket(s) {sorted(_running)} already running. Try again when it finishes.")
    ticket = await mcp_call("get_ticket_detail", {"ticket_id": ticket_id})
    if not ticket["found"]:
        raise HTTPException(404, ticket["message"])
    if ticket["status"] != "open":
        raise HTTPException(409, f"Ticket {ticket_id} is {ticket['status']}. Reset to run it again.")

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    model = active_model_name()
    _running.add(ticket_id)
    try:
        trail = audit.AuditTrail(run_id=run_id, model=model)
        toolsets = mcp_toolsets()
        router = build_router(toolsets)
        team = build_team(toolsets)
        async with router:
            result = await run_ticket(ticket, router, team, trail)
    except QuotaExhausted as exc:
        raise HTTPException(503, {
            "error": "portkey_quota_exhausted",
            "message": str(exc),
            "model": model,
            "run_id": run_id,
            "note": "The failure is in output/audit_trail.json. No other model was tried.",
        })
    except Exception as exc:
        raise HTTPException(500, {
            "error": type(exc).__name__,
            "message": str(exc),
            "model": model,
            "run_id": run_id,
        })
    finally:
        _running.discard(ticket_id)

    if "decision" not in result:
        raise HTTPException(502, {
            "error": "run_incomplete",
            "message": result.get("error"),
            "model": model,
            "run_id": run_id,
        })

    decision: BossDecision = result["decision"]
    prepared, skipped = await prepare_approvals(decision, ticket_id, run_id)
    for rec in prepared:
        trail.record(
            agent=AgentName.BOSS.value,
            action="prepared_payment",
            ticket_id=ticket_id,
            output_summary=json.dumps({k: rec[k] for k in ("id", "kind", "amount", "payee", "description")}),
            needs_human_approval=True,
        )

    # Done when the team has decided and nothing is left for a person to approve.
    if not _pending_for(_load_approvals(), ticket_id):
        ledger.set_ticket_status(ticket_id, "resolved")

    return {
        "run_id": run_id,
        "model": model,
        "ticket_id": ticket_id,
        "plan": json.loads(summarize(result["plan"])),
        "reports": [json.loads(summarize(r)) for r in result["reports"]],
        "decision": decision.model_dump(mode="json"),
        "prepared_approvals": prepared,
        "skipped_proposals": skipped,
        "ticket_status": (await mcp_call("get_ticket_detail", {"ticket_id": ticket_id}))["status"],
    }


@app.get("/events")
def list_events(
    limit: int = Query(50, ge=1, le=500),
    ticket_id: int | None = None,
    since: str | None = Query(None, description="ISO timestamp; only steps after it"),
) -> dict:
    """Recent agent-loop steps from the audit trail, newest first."""
    if not audit.AUDIT_PATH.exists():
        return {"count": 0, "events": []}
    data = json.loads(audit.AUDIT_PATH.read_text())
    steps: list[dict[str, Any]] = [
        {**s, "run_model": run.get("model")}
        for run in data.get("runs", [])
        for s in run.get("steps", [])
    ]
    if ticket_id is not None:
        steps = [s for s in steps if s.get("ticket_id") == ticket_id]
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(422, "since must be an ISO timestamp.")
        steps = [s for s in steps
                 if s.get("timestamp") and datetime.fromisoformat(s["timestamp"]) > cutoff]
    steps.sort(key=lambda s: s.get("timestamp") or "", reverse=True)
    keep = (
        "run_id", "run_model", "timestamp", "agent", "ticket_id", "action",
        "tools_called", "tool_results_summary", "output_summary",
        "needs_human_approval", "error",
    )
    events = [{k: s.get(k) for k in keep} for s in steps[:limit]]
    return {"count": len(events), "events": events}


@app.get("/approvals")
def list_approvals(status: str | None = Query(None, pattern="^(pending|approved)$")) -> dict:
    """Payments the agents prepared, waiting for (or past) human approval."""
    items = _load_approvals()
    if status:
        items = [a for a in items if a["status"] == status]
    return {"count": len(items), "approvals": items}


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the person approving")


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApproveBody) -> dict:
    """A person approved a prepared payment. This is the only route that moves money."""
    name = body.approved_by.strip()
    if not name:
        raise HTTPException(422, "approved_by can't be blank.")
    async with _approvals_lock:
        items = _load_approvals()
        rec = next((a for a in items if a["id"] == approval_id), None)
        if rec is None:
            raise HTTPException(404, f"No prepared payment {approval_id}.")
        if rec["status"] != "pending":
            raise HTTPException(409, f"{approval_id} is already {rec['status']}.")
        try:
            payment = ledger.execute_payment(
                rec["kind"], rec["target"], approved_by=name, expected_amount=rec["amount"]
            )
        except ledger.InsufficientFunds as exc:
            raise HTTPException(409, {
                "error": "insufficient_funds",
                "message": str(exc),
                "balance": exc.balance,
                "amount": exc.amount,
            })
        except ledger.PaymentError as exc:
            raise HTTPException(409, {"error": "payment_refused", "message": str(exc)})

        rec.update(status="approved", approved_by=name, approved_at=_now(), payment=payment)
        _save_approvals(items)
        resolved = not _pending_for(items, rec["ticket_id"])
        if resolved:
            ledger.set_ticket_status(rec["ticket_id"], "resolved")
    return {"approval": rec, "ticket_resolved": resolved}


@app.get("/cash")
async def cash() -> dict:
    """Current checking balance, plus what's waiting for approval against it."""
    acct = await mcp_call("get_cash_balance", {"account": "checking"})
    if not acct["found"]:
        raise HTTPException(404, acct["message"])
    pending = [a for a in _load_approvals() if a["status"] == "pending"]
    pending_total = round(sum(a["amount"] for a in pending), 2)
    return {
        "account": acct["name"],
        "balance": acct["balance"],
        "as_of": acct["date"],
        "pending_approvals": len(pending),
        "pending_total": pending_total,
        "balance_if_all_approved": round(acct["balance"] - pending_total, 2),
    }


@app.post("/reset")
async def reset() -> dict:
    """Put campus_customs_new.db back to the original values and clear prepared payments.

    The audit trail is kept: it's history, not shop state.
    """
    if _running:
        raise HTTPException(409, f"Can't reset while ticket(s) {sorted(_running)} are running.")
    async with _approvals_lock:
        info = ledger.reset_working_copy()
        _save_approvals([])
    return {**info, "approvals_cleared": True, "audit_trail_kept": True}
