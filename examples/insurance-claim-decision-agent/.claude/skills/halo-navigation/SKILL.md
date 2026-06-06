---
name: halo-navigation
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

The host wraps large tool results before you see them. Instead of the full payload
you receive a **shape map** — the data itself is held, verified, in a store out of
your context:

```
[halo] map "<mapId>" — object, N fields, stored out of context. ...
Fields:
  <mapId>.<field>   <kind>              <preview>
  <mapId>.<branch>  [branch] object{K}  ↳ child, names
```

You do **not** encode anything — that already happened. Your job is only to pull
back the specific fields you need.

## Workflow

1. Read the root kind and the per-field previews. Most steps need little or nothing
   fetched — the previews often answer them in place.
2. Decide which leaves you actually need.
3. Fetch them in **one** `mcp__halo__halo_fetch` call, passing a list of refs of
   the form `"<mapId>.<field>"`. Batch every ref a step needs; each value is
   verified on read. An entry returned with `ok=false` (e.g. `HashMismatch`) is
   untrusted — do not use it.
4. A `[branch]` ref is not a value. `halo_fetch` it to get its sub-refs, then fetch
   the specific leaf. The one `halo_fetch` both pulls and expands.
5. Use fetched values exactly as if returned inline. Do **not** fetch branches you
   do not need.

## In this agent

- **`payer_get_claim`** comes back as a halo. Fetch the service `lines` (codes,
  amounts, tooth/surface, dates) and the `diagnosis_codes`. Do **not** fetch
  `attachment_bodies` (clinical notes, x-ray meta, tooth charts) unless a specific
  line is flagged for clinical review — that bulk is the whole point of keeping it
  out of context.
- **`payer_get_claim_history`** can be large. Fetch only the lines for the code you
  are checking frequency/duplicates on.
- **`payer_get_benefit_rules`** for a whole plan is large. You should have pulled
  only this claim's codes; fetch those rule entries, not the rest.

The refs you fetched are the precise, verifiable record of what the decision rested
on — the same content-addressed handles recorded as the decision's evidence.
