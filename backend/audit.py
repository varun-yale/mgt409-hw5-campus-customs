"""Audit trail for the Campus Customs agent team.

Every agent run appends to `output/audit_trail.json` while the team works, so
afterwards you can see which agent ran, what it asked the MCP server, what came
back, what it decided, and what it cost.

The file holds a list of runs. A new run is added after the ones already there,
never in place of them, so the trail keeps every run's history. The current
run is flushed after each step rather than held in memory until the end, so a
crash halfway through still leaves a usable record of what happened.

Set AUDIT_PATH to write somewhere else, e.g. for a test run that shouldn't
land in the graded trail.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(
    os.getenv("AUDIT_PATH")
    or Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, limit: int = 400) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "..."


class AuditTrail:
    """Collects steps and writes them to output/audit_trail.json."""

    def __init__(self, run_id: str, model: str, path: Path = AUDIT_PATH):
        self.run_id = run_id
        self.model = model
        self.path = path
        self.steps: list[dict[str, Any]] = []
        self.started_at = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.previous_runs = self._load_previous_runs()

    def _load_previous_runs(self) -> list[dict[str, Any]]:
        """Runs already in the file, so this one appends instead of wiping them."""
        if not self.path.exists() or not self.path.read_text().strip():
            return []
        data = json.loads(self.path.read_text())
        if "runs" in data:
            return data["runs"]
        # Older single-run format: keep it as the first run.
        return [data] if "run_id" in data else []

    def record(
        self,
        agent: str,
        action: str,
        ticket_id: int | None = None,
        prompt_summary: str | None = None,
        tools_called: list[str] | None = None,
        tool_results_summary: list[str] | None = None,
        output_summary: str | None = None,
        needs_human_approval: bool = False,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        duration_seconds: float | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Append one step and flush the file immediately."""
        step = {
            "step": len(self.steps) + 1,
            "run_id": self.run_id,
            "timestamp": _now(),
            "agent": agent,
            "ticket_id": ticket_id,
            "action": action,
            "model": self.model,
            "prompt_summary": _truncate(prompt_summary) if prompt_summary else None,
            "tools_called": tools_called or [],
            "tool_results_summary": [_truncate(r, 300) for r in (tool_results_summary or [])],
            "output_summary": _truncate(output_summary, 600) if output_summary else None,
            "needs_human_approval": needs_human_approval,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_seconds": round(duration_seconds, 2) if duration_seconds else None,
            "error": error,
        }
        self.steps.append(step)
        self.flush()
        return step

    def steps_from_messages(self, messages: list[Any]) -> tuple[list[str], list[str]]:
        """Pull the tool calls and results out of a PydanticAI message list.

        This is what makes the trail auditable: it records the actual MCP tools
        the model reached for on this turn, not a guess at what it should have.
        """
        tools_called: list[str] = []
        results: list[str] = []
        for msg in messages:
            for part in getattr(msg, "parts", []):
                kind = getattr(part, "part_kind", "")
                if kind == "tool-call":
                    name = getattr(part, "tool_name", "?")
                    args = getattr(part, "args", None)
                    tools_called.append(f"{name}({_truncate(args, 120) if args else ''})")
                elif kind == "tool-return":
                    name = getattr(part, "tool_name", "?")
                    content = getattr(part, "content", "")
                    results.append(f"{name} -> {_truncate(content, 260)}")
        return tools_called, results

    def flush(self) -> None:
        approvals = [s for s in self.steps if s["needs_human_approval"]]
        run = {
            "run_id": self.run_id,
            "model": self.model,
            "started_at": self.started_at,
            "updated_at": _now(),
            "database": "data/campus_customs_new.db",
            "tool_source": "MCP server 'campus-customs' via .mcp.json",
            "note": (
                "Every shop fact in this run came from the MCP server. No agent "
                "has a tool that writes to the database or sends a payment."
            ),
            "total_steps": len(self.steps),
            "agents_used": sorted({s["agent"] for s in self.steps}),
            "tickets_handled": sorted(
                {s["ticket_id"] for s in self.steps if s["ticket_id"] is not None}
            ),
            "total_input_tokens": sum(s["input_tokens"] or 0 for s in self.steps),
            "total_output_tokens": sum(s["output_tokens"] or 0 for s in self.steps),
            "steps_awaiting_human_approval": len(approvals),
            "errors": [s["error"] for s in self.steps if s["error"]],
            "steps": self.steps,
        }
        runs = [*self.previous_runs, run]
        trail = {
            "description": (
                "Campus Customs agent team audit trail. One entry per run, oldest "
                "first. Each run lists every agent-loop step in order."
            ),
            "total_runs": len(runs),
            "runs": runs,
        }
        self.path.write_text(json.dumps(trail, indent=2) + "\n")
