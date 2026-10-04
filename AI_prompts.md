# HW5 — AI Prompts

MGT 409 — Homework 5: Multi-Agent Operations for Campus Customs

One section per problem: the prompt I wrote in my own words, plus any follow-up
prompts and a sentence on what the first prompt was missing.

## Problem 1: Vibe coder prompts

**What I typed:**

> Can you set up AI_prompts.md for HW5 so I can keep track of the prompts I use
> for each problem?

**Follow-up:** None.

## Problem 2: Study the Campus Customs database

**What I typed:**

> Can you look through the Campus Customs database for HW5, make the working copy
> we need for later problems, and help me understand all the tables and the three
> open tickets? Also start the harness with the tables, their fields, and a short
> explanation of why each matters.

**Follow-up:** None.

## Problem 3: Build the MCP server

**What I typed:**

> Can you build the MCP server for Problem 3 using the working database copy?
> Look at the open tickets and make three tools that would help the agents
> handle them, then document the tools in the harness and README.

**Follow-up:** None.

## Problem 4: Add the MCP server to vibe coder and test each tool

**What I typed:**

> Can you connect the MCP server to the project in .mcp.json and test the three
> tools with some realistic ticket questions? Save the results in
> output/mcp_smoke.json and check them against the database.

**Follow-up:** None.

## Problem 5: Build the agent team and grow the MCP tools

**What I typed:**

> Can you build the five-agent team in PydanticAI on gpt-6-luna and let them
> delegate to each other? Add whatever MCP tools they still need for the tickets,
> log their steps to the audit trail, and update the harness and README.

**Follow-up:** None.

## Problem 6: Plan the three tickets

**What I typed:**

> Can you make output/desk_tickets.html with tabs for tickets 101–103 plus empty
> Cash and Reflection tabs? For each ticket, write up who the Boss should call
> first, the delegations I'd expect, and which MCP tools should get used.

**Follow-up:** None.

## Problem 7: Backend routes

**What I typed:**

> Can you build the FastAPI backend in backend/main.py so the dashboard can see
> tickets, run the agents, show events, check cash, approve payments, and reset
> the database? Agents should only prepare payments, the approve route actually
> pays, and checking should never go negative.

**Follow-up:** None.

## Problem 8: Agent dashboard

**What I typed:**

> Can you build a React + Vite dashboard in frontend/ that talks to the backend?
> I want to see the tickets, run the team and watch the agents work, approve
> payments, and see the checking balance, plus a design.md explaining the look.

**Follow-up:** None.

## Problem 9: Resolve the tickets

**What I typed:**

> Can you reset the database and run tickets 101–103 through the real agent
> team? Then fill in the Actual results, Cash tab, resolved tickets, screenshots,
> and audit trail from what actually happened.

**Follow-up:**

> Can you update the Luna setup to use the Responses API so the agents can use
> their tools correctly?

The first run hit a compatibility issue with tool calling.

## Problem 10: Reflection

**What I typed:**

> Can you fill in the Reflection tab using what actually happened in the three
> real runs? Grade the agents on each ticket, compare Expected vs Actual, and
> cover the one-agent question plus new problems the team can and can't solve.

**Follow-up:** None.

## Problem 11: Submit to GitHub

**What I typed:**

> Can you clean up the HW5 folder for submission, make sure everything still
> works, check that no secrets are in it, and publish it to a public GitHub repo?

**Follow-up:** None.

---

<!--
TEMPLATE — copy this block for each problem as you work through it.
Fill it in right after you prompt, not at the end, so the log is accurate.

## Problem N: <title from the assignment>

**What I typed:**

> <the prompt, in your own words>

**Follow-up:** None.

(If there was a follow-up, replace "None." with the follow-up prompt and add one
sentence explaining what the first prompt lacked.)
-->
