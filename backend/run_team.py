"""Run the Campus Customs agent team over the open tickets.

The Boss reads each ticket and routes it, the specialists it picked report back
using MCP tools, and then the Boss makes the call. Along the way any agent can
hand a question to any other with `ask_colleague` (see agents.py), so the team
is fully connected rather than a strict hub. Every step, including each
delegation, is appended to `output/audit_trail.json` as it happens.

Run with:  .venv/bin/python backend/run_team.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic_ai.exceptions import ModelHTTPError  # noqa: E402

from agents import (  # noqa: E402
    active_model_name,
    SPECIALISTS,
    USAGE_LIMITS,
    DelegationBudget,
    TeamDeps,
    build_router,
    build_team,
    mcp_config,
    mcp_toolsets,
)
from audit import AuditTrail  # noqa: E402
from models import AgentName  # noqa: E402


class QuotaExhausted(Exception):
    """The model provider refused for billing/quota reasons. Stop the run."""


def _is_quota_error(exc: Exception) -> bool:
    return isinstance(exc, ModelHTTPError) and exc.status_code in (402, 412, 429)


def summarize(obj) -> str:
    """One readable line for the audit trail."""
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"), default=str)
    return str(obj)


async def run_ticket(ticket: dict, router, team, trail: AuditTrail) -> dict:
    tid = ticket["id"]
    print(f"\n=== ticket {tid}: {ticket['type']} — {ticket['subject']} ===")

    # 1. Boss routes the ticket.
    prompt = (
        f"Ticket {tid} is open. Type: {ticket['type']}. "
        f"Requester: {ticket['requester']}. Subject: {ticket['subject']}. "
        f"Notes: {ticket['notes']}. "
        "Decide which specialists should look at this and why."
    )
    # One delegation budget per ticket, shared by every agent working on it.
    budget = DelegationBudget()

    def deps_for(role: AgentName) -> TeamDeps:
        return TeamDeps(team=team, trail=trail, ticket_id=tid, chain=[role], budget=budget)

    t0 = time.monotonic()
    try:
        result = await router.run(prompt, usage_limits=USAGE_LIMITS)
    except Exception as exc:
        trail.record(
            agent=AgentName.BOSS.value,
            action="route_ticket",
            ticket_id=tid,
            prompt_summary=prompt,
            duration_seconds=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"  boss routing: ERROR {type(exc).__name__}: {exc}")
        if _is_quota_error(exc):
            raise QuotaExhausted(str(exc)) from exc
        return {"ticket": ticket, "error": str(exc)}
    plan = result.output
    tools, results = trail.steps_from_messages(result.all_messages())
    usage = result.usage
    trail.record(
        agent=AgentName.BOSS.value,
        action="route_ticket",
        ticket_id=tid,
        prompt_summary=prompt,
        tools_called=tools,
        tool_results_summary=results,
        output_summary=summarize(plan),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        duration_seconds=time.monotonic() - t0,
    )
    routed = [r for r in plan.route_to if r in SPECIALISTS] or SPECIALISTS
    print(f"  boss routes to: {', '.join(r.value for r in routed)}")

    # 2. Each routed specialist reports.
    reports = []
    for role in routed:
        agent = team[role]
        sp_prompt = (
            f"Ticket {tid}. Type: {ticket['type']}. Requester: {ticket['requester']}. "
            f"Subject: {ticket['subject']}. Notes: {ticket['notes']}. "
            f"sku={ticket.get('sku')} size={ticket.get('size')} qty={ticket.get('qty')} "
            f"lease_id={ticket.get('lease_id')} invoice_id={ticket.get('invoice_id')}. "
            "Look up what you need with your tools and report on your part of this."
        )
        t0 = time.monotonic()
        try:
            res = await agent.run(sp_prompt, deps=deps_for(role), usage_limits=USAGE_LIMITS)
            report = res.output
            tools, results = trail.steps_from_messages(res.new_messages())
            usage = res.usage
            trail.record(
                agent=role.value,
                action="specialist_report",
                ticket_id=tid,
                prompt_summary=sp_prompt,
                tools_called=tools,
                tool_results_summary=results,
                output_summary=summarize(report),
                needs_human_approval=report.needs_human_approval,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                duration_seconds=time.monotonic() - t0,
            )
            reports.append(report)
            flag = " [needs human approval]" if report.needs_human_approval else ""
            print(f"  {role.value}: {len(tools)} tool calls{flag}")
        except Exception as exc:  # keep the run going, but record the failure
            trail.record(
                agent=role.value,
                action="specialist_report",
                ticket_id=tid,
                prompt_summary=sp_prompt,
                duration_seconds=time.monotonic() - t0,
                error=f"{type(exc).__name__}: {exc}",
            )
            print(f"  {role.value}: ERROR {type(exc).__name__}: {exc}")
            if _is_quota_error(exc):
                raise QuotaExhausted(str(exc)) from exc

    # 3. Boss decides.
    bundle = "\n\n".join(
        f"[{r.agent.value}] summary: {r.summary}\n"
        f"recommendation: {r.recommendation}\n"
        f"blockers: {r.blockers}\n"
        f"needs_human_approval: {r.needs_human_approval}"
        for r in reports
    )
    decide_prompt = (
        f"Ticket {tid} ({ticket['type']}): {ticket['subject']}. "
        f"Notes: {ticket['notes']}.\n\n"
        f"Your specialists reported:\n\n{bundle}\n\n"
        "Make the call on this ticket."
    )
    t0 = time.monotonic()
    try:
        res = await team[AgentName.BOSS].run(
            decide_prompt, deps=deps_for(AgentName.BOSS), usage_limits=USAGE_LIMITS
        )
    except Exception as exc:
        trail.record(
            agent=AgentName.BOSS.value,
            action="final_decision",
            ticket_id=tid,
            prompt_summary=decide_prompt,
            duration_seconds=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"  boss decision: ERROR {type(exc).__name__}: {exc}")
        if _is_quota_error(exc):
            raise QuotaExhausted(str(exc)) from exc
        return {"ticket": ticket, "plan": plan, "reports": reports, "error": str(exc)}
    # The Boss agent is typed to BossDecision.
    decision = res.output
    tools, results = trail.steps_from_messages(res.new_messages())
    usage = res.usage
    trail.record(
        agent=AgentName.BOSS.value,
        action="final_decision",
        ticket_id=tid,
        prompt_summary=decide_prompt,
        tools_called=tools,
        tool_results_summary=results,
        output_summary=summarize(decision),
        needs_human_approval=decision.human_approval_required,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        duration_seconds=time.monotonic() - t0,
    )
    print(f"  decision: {decision.decision[:90]}")
    if decision.human_approval_required:
        print(f"  NEEDS HUMAN APPROVAL: {decision.approval_reason}")
    return {"ticket": ticket, "plan": plan, "reports": reports, "decision": decision}


async def main() -> int:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    model_name = active_model_name()
    trail = AuditTrail(run_id=run_id, model=model_name)
    print(f"run {run_id}  model {model_name}")

    toolsets = mcp_toolsets()
    router = build_router(toolsets)
    team = build_team(toolsets)

    async with router:
        # Pull the open tickets through MCP, not by querying the database here.
        tickets = await fetch_open_tickets(toolsets)
        trail.record(
            agent=AgentName.BOSS.value,
            action="load_tickets",
            output_summary=f"{len(tickets)} open tickets: {[t['id'] for t in tickets]}",
            tools_called=["list_open_tickets"],
        )
        print(f"{len(tickets)} open tickets\n")

        for ticket in tickets:
            try:
                await run_ticket(ticket, router, team, trail)
            except QuotaExhausted:
                print("\nModel provider quota exhausted; stopping the run. "
                      "The failure is recorded in the audit trail.")
                break

    trail.flush()
    print(f"\nwrote output/audit_trail.json  ({len(trail.steps)} steps)")
    print(f"tokens in/out: {sum(s['input_tokens'] or 0 for s in trail.steps)}/"
          f"{sum(s['output_tokens'] or 0 for s in trail.steps)}")
    return 0


async def fetch_open_tickets(toolsets) -> list[dict]:
    """Read the open tickets through the MCP server."""
    from fastmcp import Client

    async with Client(mcp_config()) as client:
        res = await client.call_tool("list_open_tickets", {})
        data = res.structured_content or json.loads(res.content[0].text)
    return data["tickets"]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
