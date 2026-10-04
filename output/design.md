# Campus Customs Ops Desk: dashboard design

The dashboard lives in `frontend/` (React + Vite + TypeScript) and talks to the
FastAPI backend at `http://localhost:8000`. Start the backend from `backend/`
with `uvicorn main:app --reload --port 8000`, then run `npm run dev` from
`frontend/` and open `http://localhost:5173`.

The goal was a screen that feels like the back office of a small shop on a busy
afternoon: you can see what's waiting, watch the team work, and sign off on
money without hunting for anything.

## Layout

Three columns under a sticky top bar.

| Area | What's there | Why |
|---|---|---|
| Top bar | Campus Customs mark, shop date, backend connection status, **Reset shop** | Context you always want: which day the shop thinks it is, and whether the backend is up. Reset sits out of the way because it wipes shop state. |
| Left | **Tickets** | The inbox. Everything starts from picking a ticket. |
| Center | Ticket header with **Run agent team**, **The team** roster, **Activity**, **Run summary** | The work itself, read top to bottom in the order it happens. |
| Right | **Checking** balance, **Needs your approval** queue | Money stays in view no matter which ticket is open, because a payment for one ticket changes what's affordable for the others. |

Below 1150px wide the columns stack, with tickets first and money last.

## How the agents are told apart

Each agent is a small CSS-drawn creature: a rounded head with two pointed ears,
eyes and a little mouth, plus a badge in the corner. They're built entirely in
HTML/CSS, with no images. Each agent gets its own color and badge glyph, so it
can be recognized by color, by symbol, or by name:

| Agent | Color | Badge | Role line |
|---|---|---|---|
| Boss | pink `#ff4fa3` | ♛ | Routes tickets, makes the call |
| Inventory | cyan `#4cc9f0` | ▦ | Stock, sizes, restocks |
| Accounting | amber `#ffc857` | $ | Invoices, cash, margins |
| Facilities | green `#7bd88f` | ⌂ | Lease and rent |
| Customer Service | violet `#b794f6` | ✉ | What the customer hears |

The Boss shares the site's pink because it's in charge. The other four sit
around the color wheel so no two are easy to confuse on near-black.

The same color follows an agent everywhere: their name in the feed, the left
edge of their speech bubble, and the top stripe of their summary card.

**The team roster** shows all five every time, so you can see who *wasn't*
involved:

- **Idle** agents are desaturated and dimmed, with "not called".
- **Involved** agents are in full color, with their step and tool-call count.
- The **active** agent (whoever spoke last during a live run) bobs gently,
  blinks, and glows.

## Tickets and resolved status

Each ticket card shows its number, subject, type, requester, and a status pill:

- **Open**: pink pill with a slowly pulsing dot, and a pink left edge on the
  card.
- **Running**: solid pink pill with a fast pulse.
- **Resolved**: green "✓ Resolved". The card goes flat and dim, its edge turns
  grey, and the subject is struck through.

Status is never shown by color alone; there's always a word and an icon. The
ticket header repeats it. An open ticket shows **Run agent team**. A resolved
one shows a large "✓ Resolved" badge with "Reset the shop to run it again" in
place of the button. If a ticket has a payment waiting, its card says so
("1 payment awaiting approval"), so you know there's still something to do.

## Watching a run

Pressing **Run agent team** starts the backend run and polls `GET /events`
every 1.2 seconds, filtered to that ticket and to steps after the moment you
clicked. Each step drops into the **Activity** feed as it's written to the audit
trail:

- The agent's creature, name, what they did ("Routed the ticket", "Filed a
  report", "Answered Accounting", "Made the call", "Prepared a payment"), and
  the time.
- **What they said**, in a speech bubble in their color.
- **Tools they used**, as small code chips (`check_stock`, `get_invoice_status`
  and so on). Hover a chip to see the arguments.
- Delegations get a dashed chip like "Facilities → Accounting", so you can follow
  who asked whom.
- Anything that needs a person gets a pink "needs approval" chip.
- At the bottom, three bouncing dots and "Agents working… 12s" until the Boss
  decides.

**Run summary** fills in when the run ends. The Boss's final call gets a wide
card at the top: decision, rationale, what needs approval, and open questions.
Below it, each specialist gets a card with their summary, recommendation, and
blockers (marked in red), plus "not confident" or "needs approval" flags. After
a page reload, the summary is rebuilt from the audit trail: each agent's step
count, the tools they used, and the last thing they said.

Every run is tagged with its run id and model. `gpt-6-luna` shows in green. Any
other model, like the earlier local `qwen2.5:7b` test run still in the history,
shows in amber, so you can't mistake it for a graded run.

## Cash and approvals

**Checking** shows the balance large, with "as of" the shop date. Under it:
how many payments are waiting and their total, and what checking would be if
all of them were approved. If that last number is negative, it turns red with
a note that checking can't go below $0. When a payment goes through, the
balance briefly flashes pink, so you notice the number changed.

**Needs your approval** is the queue of payments the agents prepared. Each card
shows the type (vendor invoice, rent, purchase), the amount in large type, the
payee, the description the backend priced from the database, and the Boss's
one-line reason. To approve:

- Enter your name in **Approving as** once; it's remembered and sent as
  `approved_by`. Until then the button reads "Enter your name to approve".
- If a payment is larger than the current balance, the card explains that it
  would overdraw checking and the button is disabled. The backend refuses it
  anyway, and if it does, the reason appears on the card.
- After approving, the balance, the ticket list, and the queue all refresh. The
  payment moves to **Recently approved** with the approver's name, and the
  ticket shows as Resolved once nothing else is waiting for it.

## When something goes wrong

- **Portkey quota (HTTP 412):** the run stops and a calm red banner explains it:
  "Portkey refused gpt-6-luna with HTTP 412 (usage limit exceeded). The run
  stopped, the failure is recorded in the audit trail, and no other model was
  tried." The run id is included. The failed step appears in the feed with the
  raw error, and the button works again right away.
- **Backend not running:** the connection pill turns red, and a banner with a
  **Retry** button says the backend at `localhost:8000` can't be reached.
- **Only one run at a time:** while a ticket runs, other tickets' buttons read
  "Another ticket is running", and Reset is disabled.

## Creative choices

- **Black-and-pink on purpose.** Near-black surfaces, a soft pink glow in the
  top corner, and pink for anything you can act on (run, approve, open
  tickets). Text stays high-contrast white or light grey.
- **Characters, not icons.** The agents are little desk creatures with ears and
  eyes, so the activity feed reads like a team chat instead of a log file.
- **Motion with meaning.** Pulsing means open, bobbing means working, a flash
  means money moved, and new items rise in gently. Everything stops for users
  who turn on reduced motion.
- **Money always visible.** Because one ticket's payment changes what the next
  one can afford, cash and approvals never scroll out of view.
- **Honest labels.** Model tags, "Rebuilt from the audit trail", and "not
  called" mean the dashboard never makes a run look better than it was.
