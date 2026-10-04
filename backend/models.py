"""Shared data types for the Campus Customs agent team.

These are the shapes the agents hand back. Keeping the replies typed means a
specialist can't answer with a loose paragraph that the Boss then has to parse,
and it makes the audit trail consistent.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    """The five roles on the team."""

    BOSS = "boss"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"


class Risk(str, Enum):
    """How much trouble acting on a recommendation could cause."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Fact(BaseModel):
    """One shop fact an agent pulled from the MCP server.

    Agents are told to record the tool they got it from, so a human reading the
    audit trail can tell the difference between a looked-up number and a guess.
    """

    field: str = Field(description="What the value is, e.g. 'stock of CC-TEE-WHITE size S'")
    value: str = Field(description="The value as returned by the tool")
    source_tool: str = Field(description="MCP tool the value came from")


class SpecialistReport(BaseModel):
    """What Inventory, Accounting, Facilities, or Customer Service hands back."""

    agent: AgentName
    ticket_id: int | None = Field(default=None, description="Ticket this is about")
    summary: str = Field(description="Two or three sentences on what was found")
    facts: list[Fact] = Field(
        default_factory=list, description="Shop facts used, each with its tool"
    )
    recommendation: str = Field(description="What the shop should do next")
    blockers: list[str] = Field(
        default_factory=list,
        description="Anything stopping the recommendation from being carried out",
    )
    needs_human_approval: bool = Field(
        default=False,
        description="True when carrying this out means spending money or promising a customer something",
    )
    risk: Risk = Field(default=Risk.NONE)
    confident: bool = Field(
        default=True,
        description="False when a needed fact was missing from the database",
    )


class TicketPlan(BaseModel):
    """The Boss's decision on one ticket."""

    ticket_id: int
    ticket_type: str
    route_to: list[AgentName] = Field(
        description="Which specialists should look at this ticket, in order"
    )
    reason: str = Field(description="Why those specialists, in one or two sentences")


class PaymentKind(str, Enum):
    """What a prepared payment is for."""

    INVOICE = "invoice"
    RENT = "rent"
    PURCHASE = "purchase"


class ProposedPayment(BaseModel):
    """A payment the Boss wants a human to approve.

    There is no amount field on purpose. The backend looks the amount up from
    the database when it prepares the approval, so an agent can't invent one.
    Proposing a payment does not pay it.
    """

    kind: PaymentKind
    invoice_id: int | None = Field(default=None, description="For kind=invoice")
    lease_id: int | None = Field(default=None, description="For kind=rent")
    sku: str | None = Field(default=None, description="For kind=purchase")
    size: str | None = Field(default=None, description="For kind=purchase")
    qty: int | None = Field(default=None, description="For kind=purchase: units to buy")
    vendor_id: int | None = Field(default=None, description="For kind=purchase")
    reason: str = Field(description="One sentence on why this should be paid")


class BossDecision(BaseModel):
    """The Boss's closing call on a ticket after the specialists report."""

    ticket_id: int
    decision: str = Field(description="What the shop is going to do")
    rationale: str = Field(description="Why, referencing the facts the specialists found")
    human_approval_required: bool = Field(
        description="True if this involves paying money or committing to a customer"
    )
    approval_reason: str | None = Field(
        default=None, description="What specifically needs a person to sign off"
    )
    proposed_payments: list[ProposedPayment] = Field(
        default_factory=list,
        description="Payments for a human to approve. Leave empty if nothing should be paid.",
    )
    open_questions: list[str] = Field(default_factory=list)


class AuditStep(BaseModel):
    """One step in the agent loop, written to output/audit_trail.json."""

    step: int
    run_id: str
    timestamp: str
    agent: AgentName
    ticket_id: int | None = None
    action: str = Field(description="What happened: 'agent_run', 'tool_call', 'decision'")
    model: str
    prompt_summary: str | None = None
    tools_called: list[str] = Field(default_factory=list)
    tool_results_summary: list[str] = Field(default_factory=list)
    output_summary: str | None = None
    needs_human_approval: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
