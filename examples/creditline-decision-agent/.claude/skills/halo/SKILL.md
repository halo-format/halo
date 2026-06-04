---
name: halo
description: >-
  Navigate Halo envelopes. Use whenever a tool result comes back not as the full
  payload but as a halo envelope — a compact map with a `view.summary`, named
  `branches`, and a `source.id`. Read the map and fetch only the fields you need
  with the halo_fetch / halo_walk tools instead of expecting the whole payload.
  Triggers on any `{"halo":"1", ...}` tool output or a "[halo] …" note.
allowed-tools:
  - mcp__halo__halo_walk
  - mcp__halo__halo_fetch
---

# Halo: navigating large tool results

The host wraps large tool results before you see them. Instead of the full
payload you receive a **halo envelope** — the data itself is held, verified, in a
store out of your context:

```json
{ "halo": "1", "view": { "summary": "...", "branches": { "<name>": "<handle>" } },
  "source": { "id": "<mapId>" } }
```

You do **not** encode anything — that already happened. Your job is only to pull
back the specific fields you need.

## Workflow

1. Read `view.summary` and the branch names under `view.branches` to see what the
   result contains.
2. Decide which leaves you actually need for the task.
3. Fetch them in **one** `mcp__halo__halo_fetch` call, passing a list of refs of
   the form `"<mapId>.<branch>"` — e.g. `["m1.credit_score", "m1.total_outstanding_debt"]`.
   Batch every ref a step needs into that single call; each value is verified on
   read. An entry returned with `ok=false` (e.g. `HashMismatch`) is untrusted —
   do not use it.
4. If a branch is itself large, call `mcp__halo__halo_walk` on its ref first to
   see its sub-structure, then fetch the specific leaf.
5. Use the fetched values exactly as if they had been returned inline. Do **not**
   fetch branches you do not need.

## In this agent

A bureau report comes back as a halo. The decision needs only `credit_score`,
`total_outstanding_debt`, `delinquencies_24m`, `hard_inquiries_6m`, and
`bureau_report_id` — fetch those leaves in one call. Do **not** fetch the
`tradelines`, `recent_inquiries`, or `public_records` bulk; the policy never reads
them, and the point is to keep them out of context. The refs you fetched are the
precise, verifiable record of what the decision rested on.
