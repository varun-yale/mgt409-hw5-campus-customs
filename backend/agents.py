"""The five Campus Customs agents, built with PydanticAI.

Boss, Inventory, Accounting, Facilities, and Customer Service. Each one loads
its own prompt from `backend/prompts/`, and every shop fact any of them uses
comes from the MCP server defined in `.mcp.json`. There is no second tools layer
that touches the database directly.

The team is fully connected: every agent carries an `ask_colleague` tool and can
hand a question to any of the other four, with caps on depth and on asks per
ticket so delegation can't loop.

All five run on gpt-6-luna through the Portkey gateway. No other model is used.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import load_mcp_toolsets
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset
from pydantic_ai.usage import UsageLimits

from models import AgentName, BossDecision, SpecialistReport, TicketPlan

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
MCP_CONFIG = ROOT / ".mcp.json"

# The model the assignment requires. This is the default and it is what a
# graded run must use.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Caps per agent run. A confused model that keeps calling tools costs money and
# time, so the loop is bounded rather than trusted to stop on its own.
USAGE_LIMITS = UsageLimits(request_limit=6, tool_calls_limit=10)

# HW5/.env (copied from .env.example) holds the Portkey settings and wins over
# anything already exported in the shell.
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env", override=True)

# .mcp.json uses ${HW5_PYTHON} and ${HW5_ROOT} instead of absolute paths, so the
# repo works wherever it is cloned. Point them at this interpreter and folder.
os.environ.setdefault("HW5_PYTHON", sys.executable)
os.environ.setdefault("HW5_ROOT", str(ROOT))


def _expand(value: Any) -> Any:
    """Fill in ${VAR} / ${VAR:-default} the same way pydantic-ai does for .mcp.json."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            name, default = m.group(1), m.group(3)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise ValueError(f"{name} is referenced in .mcp.json but not set.")
        return re.sub(r"\$\{(\w+)(:-([^}]*))?\}", sub, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def mcp_config() -> dict:
    """.mcp.json with its variables filled in, for code that talks to MCP directly."""
    return _expand(json.loads(MCP_CONFIG.read_text()))


def active_model_name() -> str:
    """The model every agent runs on. There is only one, so the audit trail
    always records gpt-6-luna."""
    return MODEL_NAME


def build_model() -> OpenAIResponsesModel:
    """Build the model for all five agents: gpt-6-luna over Portkey, nothing else.

    PORTKEY_PROVIDER is the provider slug of the Portkey integration to route
    to (sent as the x-portkey-provider header). There is no alternative backend
    and no fallback: if either setting is missing, this raises instead of
    reaching for a different model.
    """
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Put it in HW5/.env.")
    portkey_provider = os.getenv("PORTKEY_PROVIDER")
    if not portkey_provider:
        raise RuntimeError(
            "PORTKEY_PROVIDER is not set. Put your Portkey integration's provider slug "
            "in HW5/.env, e.g. PORTKEY_PROVIDER=@your-provider-slug."
        )
    # Portkey's provider-slug setup: authenticate to Portkey with x-portkey-api-key
    # and route with x-portkey-provider. Portkey supplies the OpenAI credential
    # stored in that integration. The SDK's own Authorization header gets a
    # placeholder, so the Portkey key is never forwarded to OpenAI.
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key="portkey-managed",
        default_headers={
            "x-portkey-api-key": api_key,
            "x-portkey-provider": portkey_provider,
        },
    )
    # Responses API (/v1/responses): gpt-6-luna only accepts function tools
    # alongside reasoning on this endpoint, not on /v1/chat/completions.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing prompt file: {path}")
    return path.read_text()


# Which MCP tools each role is allowed to reach for. Least privilege: Customer
# Service has no reason to read the cash balance, and Facilities has no reason
# to price hoodies. Narrower tool lists also mean fewer tokens per call.
TOOL_ACCESS: dict[AgentName, set[str]] = {
    AgentName.BOSS: {
        "get_shop_date",
        "list_open_tickets",
        "get_ticket_detail",
    },
    AgentName.INVENTORY: {
        "get_shop_date",
        "get_ticket_detail",
        "check_stock",
        "get_vendor_lead_time",
        "get_invoice_status",
    },
    AgentName.ACCOUNTING: {
        "get_shop_date",
        "get_ticket_detail",
        "get_invoice_status",
        "list_open_invoices",
        "get_cash_balance",
        "get_price_and_margin",
        "list_payments_made",
    },
    AgentName.FACILITIES: {
        "get_shop_date",
        "get_ticket_detail",
        "check_rent_status",
        "get_cash_balance",
        "list_open_invoices",
    },
    AgentName.CUSTOMER_SERVICE: {
        "get_shop_date",
        "list_open_tickets",
        "get_ticket_detail",
        "check_stock",
        "get_invoice_status",
    },
}


def _base_name(tool_name: str) -> str:
    """Strip the server prefix load_mcp_toolsets adds (e.g. 'campus-customs_')."""
    return tool_name.split("_", 1)[-1] if tool_name.startswith("campus") else tool_name


def mcp_toolsets() -> list[AbstractToolset]:
    """Load the MCP server from .mcp.json. This is the only path to shop data."""
    return load_mcp_toolsets(MCP_CONFIG)


def toolsets_for(role: AgentName, toolsets: list[AbstractToolset]) -> list[AbstractToolset]:
    allowed = TOOL_ACCESS[role]

    def keep(_ctx, tool_def) -> bool:
        name = tool_def.name
        return name in allowed or _base_name(name) in allowed or any(
            name.endswith(a) for a in allowed
        )

    return [ts.filtered(keep) for ts in toolsets]


# Delegation caps. Any agent can ask any other agent, but a chain of asks stops
# two hops deep, nobody can be asked twice in the same chain, and each ticket
# gets a fixed number of asks in total. Without these, two agents can bounce a
# question back and forth and burn tokens until the request limit hits.
MAX_DELEGATION_DEPTH = 2
DELEGATIONS_PER_TICKET = 6


@dataclass
class DelegationBudget:
    remaining: int = DELEGATIONS_PER_TICKET


@dataclass
class TeamDeps:
    """What every agent run carries: who is on the team and how it got here.

    `chain` is the list of agents from the one the runner started down to the
    one currently answering, so `chain[-1]` is always "me".
    """

    team: dict[AgentName, Agent]
    trail: Any
    ticket_id: int | None
    chain: list[AgentName]
    budget: DelegationBudget = field(default_factory=DelegationBudget)

    @property
    def me(self) -> AgentName:
        return self.chain[-1]


def _summarize_output(output: Any) -> str:
    if hasattr(output, "model_dump"):
        return json.dumps(output.model_dump(mode="json"), default=str)
    return str(output)


delegation = FunctionToolset()


@delegation.tool
async def ask_colleague(
    ctx: RunContext[TeamDeps], colleague: AgentName, question: str
) -> str:
    """Hand a question to another agent on the team and get their answer back.

    Use this when the answer depends on something another role owns and your own
    tools can't see it. Inventory owns stock and lead times, Accounting owns
    invoices, cash, and pricing, Facilities owns leases and rent, Customer
    Service owns what the customer is told, and the Boss owns final calls.

    Args:
        colleague: who to ask: boss, inventory, accounting, facilities, or
            customer_service. Not yourself.
        question: a specific question, with the sku, size, invoice id, or lease
            id they need to look it up.
    """
    deps = ctx.deps
    caller = deps.me

    if colleague == caller:
        return "You can't delegate to yourself. Use your own tools."
    if colleague in deps.chain:
        path = " -> ".join(a.value for a in deps.chain)
        return f"Refused: {colleague.value} is already in this chain ({path}). Answer with what you have."
    if len(deps.chain) > MAX_DELEGATION_DEPTH:
        return "Refused: delegation depth limit reached. Answer with what you have."
    if deps.budget.remaining <= 0:
        return "Refused: this ticket's delegation budget is used up. Answer with what you have."
    deps.budget.remaining -= 1

    child = replace(deps, chain=[*deps.chain, colleague])
    prompt = (
        f"{caller.value} is asking you about ticket {deps.ticket_id}: {question}\n"
        "Look up what you need with your own tools and answer for your part only."
    )
    t0 = time.monotonic()
    try:
        res = await deps.team[colleague].run(prompt, deps=child, usage_limits=USAGE_LIMITS)
    except Exception as exc:
        deps.trail.record(
            agent=colleague.value,
            action=f"delegated_by_{caller.value}",
            ticket_id=deps.ticket_id,
            prompt_summary=prompt,
            duration_seconds=time.monotonic() - t0,
            error=f"{type(exc).__name__}: {exc}",
        )
        return f"{colleague.value} could not answer ({type(exc).__name__}). Treat this as unknown."

    tools, results = deps.trail.steps_from_messages(res.new_messages())
    usage = res.usage
    output = res.output
    needs_approval = getattr(output, "needs_human_approval", None) or getattr(
        output, "human_approval_required", False
    )
    deps.trail.record(
        agent=colleague.value,
        action=f"delegated_by_{caller.value}",
        ticket_id=deps.ticket_id,
        prompt_summary=prompt,
        tools_called=tools,
        tool_results_summary=results,
        output_summary=_summarize_output(output),
        needs_human_approval=bool(needs_approval),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        duration_seconds=time.monotonic() - t0,
    )
    return f"Answer from {colleague.value}: {_summarize_output(output)}"


def build_agent(role: AgentName, toolsets: list[AbstractToolset]) -> Agent:
    """One agent for one role, with its prompt file, its slice of the MCP tools,
    and `ask_colleague` so it can delegate to any of the other four."""
    output_type = BossDecision if role is AgentName.BOSS else SpecialistReport
    return Agent(
        build_model(),
        instructions=load_prompt(role.value),
        output_type=output_type,
        deps_type=TeamDeps,
        toolsets=[*toolsets_for(role, toolsets), delegation],
        name=role.value,
        retries=2,
    )


def build_router(toolsets: list[AbstractToolset]) -> Agent:
    """The Boss wearing its routing hat: decides who should see a ticket."""
    return Agent(
        build_model(),
        instructions=load_prompt("boss"),
        output_type=TicketPlan,
        toolsets=toolsets_for(AgentName.BOSS, toolsets),
        name="boss_router",
        retries=2,
    )


def build_team(toolsets: list[AbstractToolset]) -> dict[AgentName, Agent]:
    """All five agents, keyed by role."""
    return {role: build_agent(role, toolsets) for role in AgentName}


SPECIALISTS = [
    AgentName.INVENTORY,
    AgentName.ACCOUNTING,
    AgentName.FACILITIES,
    AgentName.CUSTOMER_SERVICE,
]
