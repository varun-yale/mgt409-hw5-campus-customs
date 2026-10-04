# Campus Customs — Multi-Agent Operations Desk

MGT 409, Homework 5. A five-agent team (Boss, Inventory, Accounting, Facilities,
Customer Service) works the Campus Customs back-office tickets. Agents get shop
facts only through an MCP server over a SQLite database, can prepare payments
but never send them, and a person approves every payment from a React
dashboard. Every agent step is written to an audit trail.

## What's in the repo

```
HW5/
├── AI_prompts.md          prompt log, one entry per problem
├── README.md
├── requirements.txt       Python dependencies
├── .env.example           settings template (copy to .env)
├── .mcp.json              how the backend/agents launch the MCP server
├── data/
│   ├── campus_customs.db       original database (never modified)
│   └── campus_customs_new.db   working copy the system reads and writes
├── mcp_server/            FastMCP server: 12 read-only tools + ledger for human-approved writes
├── backend/               FastAPI app (main.py), the five PydanticAI agents, prompts, audit trail
├── frontend/              React + Vite + TypeScript dashboard
└── output/                homework deliverables (see below)
```

## Setup

You need Python 3.11+ and Node 20+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..

cp .env.example .env      # then fill in your Portkey values
```

`.env` needs two values:

| Variable | What it is |
|---|---|
| `PORTKEY_API_KEY` | Your Portkey API key. Sent as `x-portkey-api-key`. |
| `PORTKEY_PROVIDER` | The Portkey provider slug that serves `gpt-6-luna`, e.g. `@openai-personal`. Sent as `x-portkey-provider`. |

All agents use `gpt-6-luna` through `https://api.portkey.ai/v1` (Responses API).
There is no fallback model: if either setting is missing, runs are refused.

## Running it

Start the backend, then the dashboard, in two terminals with the venv active:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Pick a ticket, press **Run agent team**, watch the
agents work in the Activity feed, and approve any prepared payment in the
right-hand queue. **Reset shop** copies the original database back over the
working copy for a fresh run. The audit trail is kept.

The backend starts the MCP server on its own using `.mcp.json`. That file has no
machine-specific paths: `${HW5_PYTHON}` and `${HW5_ROOT}` are filled in by
`backend/agents.py`.

## Safety rules

- Agents can only read the database through MCP. No tool writes or pays.
- The Boss can propose payments without amounts. The backend prices them from
  the database, and only `POST /approvals/{id}/approve` moves money, after a
  person approves it by name.
- A payment that would take checking below $0 is refused.
- Delegation between agents is capped: no loops, two hops deep, six asks per
  ticket, and six model requests per agent run.

## Deliverables (`output/`)

| File | Contents |
|---|---|
| `harness.md` | Tables, MCP tools, the five agents, API routes, dashboard, safety rules |
| `mcp_smoke.json` | Each MCP tool tested over MCP and checked against the database |
| `desk_tickets.html` | Expected plans, actual results, Cash tab and Reflection for tickets 101–103 |
| `design.md` | Dashboard design notes |
| `audit_trail.json` | Every agent run, including the three real gpt-6-luna runs that resolved the tickets |
| `resolved_tickets.json` | Final status, outcome, agent contributions and approvals per ticket |
| `resolved_board.html` | Dashboard screenshots of each resolved ticket (`resolved_board/*.png`) |

Starting checking was $3,400. Approved payments were $840 (invoice 501) and
$2,400 (rent). The ending balance is $160, and all three tickets are resolved.
