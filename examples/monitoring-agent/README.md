# Production Monitoring Agent (TypeScript · Claude Agent SDK)

A self-contained monitoring agent that triages **Sentry-shaped** issues,
diagnoses them against **Datadog/Loki-shaped** logs, and declares/resolves
**PagerDuty-shaped** incidents — all through a human-gated, **Halo**-backed tool
layer over a local Postgres. No external credentials required.

Built on `@anthropic-ai/claude-agent-sdk` (TypeScript) with Skills, and a custom
stdio MCP server.

## The guiding idea

The **tool contract is the swap point.** Today each tool body is SQL on `ext.*`;
later it is an API call to Sentry / the logs backend / PagerDuty. Because the
local `ext.*` tables are shaped like the external systems, that swap is
mechanical — the skills, the approval gate, and Halo are untouched.

```
 schedule / webhook ─▶ orchestrator (Claude Agent SDK) ◀── skills (triage, diagnose,
                              │   ▲                          incident-response, halo-navigation)
                              │   │ Halo adapter: PostToolUse hook → shape map; halo_fetch
                              │ mcp tool call
                              ▼
                     monitoring MCP server ─▶ local Postgres  (ext.* mirrors Sentry + logs + PagerDuty)
                              ▼
                     write gate ─▶ agent.approvals ─▶ human confirm ─▶ commit (ext.incidents)
```

One Postgres, two schemas: `ext.*` stands in for the external systems and is
shaped like them; `agent.*` is the agent's own state (sessions, the Halo store,
approvals, triage) and never changes when you integrate.

## Halo (the part that matters)

Large tool results don't belong in the model's context. This example measures the
**consumer-side Halo adapter** ([`@halo-format/claude`](../../ts/packages/claude),
`installHalo`): a `PostToolUse` hook encodes any large tool result into a
content-addressed store and replaces what the model sees with a compact **shape map**
— the root kind, then one line per field (its `ref`, its kind, and a bounded preview).
The model pulls back only the fields a step needs with a single `halo_fetch(refs)`
tool, verified on read; a ref that lands on a `[branch]` returns its sub-refs, so one
tool both reads and expands. The store is shared across the run, so a ref seen early is
fetchable late, and repeated lookups of one issue fold into a growing map
(argument-join). See the **halo-navigation** skill for the navigation guidance.

In the A/B harness the MCP server itself runs **raw** (`MONITORING_HALO=0`) in every
arm, so the only variable is the adapter. (The server also ships an *optional*
built-in Halo path in `src/mcp/halo.ts` — `halo_fetch` / `halo_fetch_many` over
`agent.halo_nodes` — but it is off in the comparison; the adapter is what's measured.)

## Tools (`src/mcp/server.ts`)

| Tool | Kind | Notes |
|------|------|-------|
| `list_open_issues` | read | ranked open issues; large `full_list` payload |
| `get_issue_detail` | read | stacktrace / breadcrumbs / tags / events for one issue |
| `search_logs` | read | windowed log slice; `lines` / `errors` |
| `list_incidents` | read | lightweight |
| `triage_note` | write | direct, low risk |
| `declare_incident` | write | **human-gated**; dedup_key = issue_id |
| `resolve_incident` | write | **human-gated** |
| `acknowledge_incident` / `assign_incident` | write | direct, low risk |
| `halo_fetch` / `halo_fetch_many` | read | *optional* server-side Halo drill (off in the A/B; the adapter is what's measured) |

The three heavy reads (`list_open_issues`, `get_issue_detail`, `search_logs`) are the
payloads the Halo adapter shrinks — they return raw here and the `PostToolUse` hook
wraps them into a shape map before the model sees them.

Every call is recorded in `agent.tool_calls` (tool, args, result root handle,
latency, outcome) — the eval/observability trail.

## Quick start

```bash
# 1. Postgres (reuses the shared local instance on :5433)
#    From elsewhere in this repo: docker compose -f ../creditline-decision-agent/docker-compose.yml up -d
#    …or any Postgres reachable via MONITORING_DB_DSN.

# 2. Install + configure
npm install
cp .env.example .env

# 3. Create the `monitoring` database, apply schema, seed ext.*
npm run initdb

# 4a. Deterministic demo (no model key) — drives the real MCP server over stdio
npm run demo

# 4b. Live agent (Claude Agent SDK; uses your `claude` login or ANTHROPIC_API_KEY)
npm run agent
#     …in a second terminal, act as on-call to resolve the gated writes:
npm run oncall            # interactive
#   (or, unattended for a hands-off run:)  npm run oncall -- auto
```

The seeded **hero issue** `4502913` (BACKEND-12A) — a `TypeError` in
`checkout.completeOrder` affecting 412 users, with a matching error spike on
`checkout-api` — is the case the agent triages, diagnoses, and declares.

## Token comparison (baseline vs Halo vs TOON)

The Halo adapter packages are part of this monorepo but not published to npm, so
they are **built and vendored** into this example's `node_modules` (they are not in
`package.json`). One-time setup:

```bash
# 1. Build the core + Claude adapter in the monorepo
( cd ../../ts && pnpm --filter @halo-format/halo build && pnpm --filter @halo-format/claude build )

# 2. Vendor the built packages into this example's node_modules
bash scripts/vendor-halo.sh
#    Re-run this after ANY `npm install` — npm prunes them as "extraneous".
```

Then run the three arms (the MCP server runs raw in all of them; only the adapter /
serialization format changes):

```bash
scripts/run_token_ab.sh baseline   # raw JSON results
scripts/run_token_ab.sh halo       # our @halo-format/claude adapter (PostToolUse hook + shape map)
scripts/run_token_ab.sh toon       # results serialized as TOON (compact, but still in-context)
```

Each run writes `runs/<label>.json` (token summary) and `runs/<label>.events.json`
(the full ordered event timeline — assistant text, tool calls, and tool results with
byte counts and the shape map). The `runs/` directory is local-only (git-ignored). A
live agent is non-deterministic, so run each arm a few times and compare means rather
than a single run. Model: `claude-sonnet-4-6` (set via `.env`).

## The swap to real systems, later

You touch only the tool bodies in `src/mcp/server.ts`:
`list_open_issues` / `get_issue_detail` → Sentry issues/events endpoints;
`search_logs` → the logs backend query API; `declare_incident` /
`resolve_incident` → PagerDuty Events API v2 passing `dedup_key = issue_id`.
Nothing else moves — `ext.*` was built to the external systems' shape.
