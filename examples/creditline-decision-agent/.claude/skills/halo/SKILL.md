---
name: halo
description: >-
  Navigate Halo shape maps. Use whenever a large tool result comes back not as the
  full payload but as a halo shape map — a "[halo] map …" note with a root kind and
  one line per field (ref, kind, and a bounded preview). Read the previews and fetch
  only the fields you still need with the halo_fetch tool instead of expecting the
  whole payload. Triggers on any "[halo] …" tool output.
allowed-tools:
  - mcp__halo__halo_fetch
---

# Halo: navigating large tool results

The host wraps large tool results before you see them. Instead of the full
payload you receive a **shape map** — the data itself is held, verified, in a
store out of your context:

```
[halo] map "<mapId>" — object, N fields, stored out of context. ...
Fields:
  <mapId>.<field>   <kind>              <preview>
  <mapId>.<branch>  [branch] object{K}  ↳ child, names
```

You do **not** encode anything — that already happened. Your job is only to pull
back the specific fields you need.

## Workflow

1. Read the root kind and the per-field previews to see what the result contains.
   The previews are sized to let you decide; most steps need to fetch little or
   nothing.
2. Decide which leaves you actually need for the task.
3. Fetch them in **one** `mcp__halo__halo_fetch` call, passing a list of refs of
   the form `"<mapId>.<field>"` — e.g. `["m1.credit_score", "m1.total_outstanding_debt"]`.
   Batch every ref a step needs into that single call; each value is verified on
   read. An entry returned with `ok=false` (e.g. `HashMismatch`) is untrusted —
   do not use it.
4. A `[branch]` ref is not a value. `halo_fetch` it to get its sub-refs (it comes
   back as `kind:"branch"` with the child fields), then fetch the specific leaf.
   There is no separate walk tool — the one `halo_fetch` both pulls and expands.
5. Use the fetched values exactly as if they had been returned inline. Do **not**
   fetch branches you do not need.

## In this agent

A bureau report comes back as a halo. The decision needs only `credit_score`,
`total_outstanding_debt`, `delinquencies_24m`, `hard_inquiries_6m`, and
`bureau_report_id` — fetch those leaves in one call. Do **not** fetch the
`tradelines`, `recent_inquiries`, or `public_records` bulk; the policy never reads
them, and the point is to keep them out of context. The refs you fetched are the
precise, verifiable record of what the decision rested on.
