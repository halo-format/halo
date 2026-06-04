---
name: halo-navigation
description: >-
  How to work with Halo envelopes efficiently: read the summary, fetch only what
  the step needs, batch drill-downs into one call, and slice logs rather than
  pulling the whole window. Applies to every heavy read.
allowed-tools:
  - mcp__halo__halo_fetch
---

# Halo navigation

Heavy reads (`list_open_issues`, `get_issue_detail`, `search_logs`) are withheld
and replaced by a **shape map**, not the raw payload:

```
[halo] map "<id>" — object, N fields, stored out of context. ...
Fields:
  <id>.<field>  <kind>  <preview>
  <id>.<branch> [branch] object{K}  ↳ child, names
```

Rules that keep a long run cheap:

1. **Read the shape map first.** The root kind and per-field previews are sized
   to let you triage and decide. Most steps never need to fetch anything.
2. **One tool: `mcp__halo__halo_fetch(refs)`.** It takes an ARRAY of refs and is
   the only navigation tool. A value ref (e.g. `<id>.stacktrace`) returns its
   value; a `[branch]` ref returns its sub-refs to fetch next. Never fetch
   `full_list` or a whole log window just to "look" — fetch the specific field.
3. **Batch drill-downs.** When a step needs several fields, pass them together:
   `halo_fetch(["<id>.stacktrace", "<id>.breadcrumbs"])` — one round trip, not N.
4. **Slice logs.** Prefer the `errors` field or a narrower `search_logs` window
   over the full `lines` payload.
5. **Reuse the map.** `get_issue_detail` folds repeated lookups of the same
   issue into one growing map; a ref seen earlier in the run is still fetchable
   later — don't re-pull data you already have.

Refs resolve to stable content addresses, so the same data is never re-sent
turn after turn. That compounding saving is the whole point.
