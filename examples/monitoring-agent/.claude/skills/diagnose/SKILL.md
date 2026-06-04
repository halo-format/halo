---
name: diagnose
description: >-
  For a chosen issue, fetch the stacktrace and the breadcrumb near the error,
  slice logs around the spike, and form a hypothesis grounded in the data. Use
  after triage, before proposing an incident.
allowed-tools:
  - mcp__monitoring__get_issue_detail
  - mcp__monitoring__search_logs
  - mcp__halo__halo_fetch
---

# Diagnose

When a heavy read is withheld you get a halo SHAPE MAP: the map id + root kind,
then one line per field (its `<mapId>.<field>` ref, its kind, and a preview).
`mcp__halo__halo_fetch` is the only navigation tool — pass an array of refs and
batch everything a step needs into ONE call.

1. **Detail** — `get_issue_detail(issue_id)`. The shape map (id = the issue id)
   lists `issue`, `latest_event`, `n_events`, `stacktrace`, `breadcrumbs`,
   `tags`, `events`. The previews often already show the exception and the
   culprit frame.

2. **Drill in (one call)** — fetch only what you need, together:
   `halo_fetch(["<id>.stacktrace", "<id>.breadcrumbs"])`. Find the top **in-app**
   frame (`in_app: true`, has a `context_line`) — that is the culprit. Read the
   breadcrumb immediately before the error for what happened just prior.

3. **Correlate with logs** — `search_logs` scoped to the relevant service/level
   and window (e.g. `{ service, level: "error" }`). Reason on the preview fields
   (`error_count`, `by_service`, `window`); `halo_fetch(["<id>.errors"])` for the
   error slice only. Do not pull the whole window (`lines`).

4. **Hypothesis** — state the likely cause in one or two sentences, citing the
   frame, the breadcrumb, and the correlated log spike. This feeds the
   **incident-response** skill.
