# Insurance Claim Decision Agent — TypeScript (raw Claude API)

A **TypeScript** port of the [`insurance-claim-decision-agent`](../insurance-claim-decision-agent)
that runs on the **raw Claude Messages API** (`@anthropic-ai/sdk`) with a hand-built
tool-use loop — no Agent SDK, no CLI. Same agent, same architecture, a different
language *and* a different runtime.

It adjudicates a submitted claim and decides each service line — **pay**, **deny**,
**reduce**, or **pend** for human review — with the patient responsibility and the
standard X12 reason codes (CARC/RARC). The model orchestrates and selects reason
codes; a **deterministic engine** computes every dollar; a **human owns** every
denial, reduction, or pend.

## How it differs from the Python example

| | Python (`insurance-claim-decision-agent`) | This (TypeScript) |
|---|---|---|
| Runtimes | Claude Agent SDK / CLI **and** raw API | **raw Messages API** only |
| Tool transport | MCP server (stdio) + in-process loop | raw tool defs, in-process loop |
| Halo | adapter `PostToolUse` hook *or* by-hand | **by hand** (`@halo-format/halo` core) |

Everything else is a faithful port: the **same `ext.*`/`agent.*` SQL schema** (reused
verbatim), the same deterministic engine, the same 13 tools, the same human-review
gate, and the same seeded claims. Evidence handles are computed with the published
`@halo-format/halo` core, so they're **byte-identical to the Python port**.

## The tool-use loop (raw API)

`src/run-raw-api.ts` is a manual loop:

```
messages.create({ system, tools, messages })
  → if stop_reason === "tool_use": run each tool in-process, append tool_result, repeat
  → else: done
```

The 13 payer tools are declared as raw tool definitions (`src/tools.ts` → `TOOL_DEFS`)
and dispatched to the same functions that hold the SQL. With **`HALO=1`**, a large
tool result is encoded into a Halo store *by hand* (the raw API has no hook), the
model is handed the **shape map** instead of the payload, and a `halo_fetch` tool
pulls back only the fields it needs (verified on read).

## Quick start

```bash
# 1. Postgres (single engine; database mimic_payer — shared with the Python example)
#    From either example: docker compose up -d   (see ../insurance-claim-decision-agent)

# 2. Deps + config
npm install
cp .env.example .env             # set ANTHROPIC_API_KEY, DB DSN

# 3. Schema + agent role + seed (reuses the same .sql as the Python example)
set -a && . ./.env && set +a
bash scripts/init_db.sh

# 4a. No-API-key smoke test of tool dispatch + Halo encode/fetch
npx tsx src/run-raw-api.ts CLM-PROF --selftest

# 4b. The agent, raw API (CLM-PROF auto-finalizes — no examiner needed)
HALO=0 RUN_LABEL=raw_baseline npx tsx src/run-raw-api.ts CLM-PROF
HALO=1 RUN_LABEL=raw_halo     npx tsx src/run-raw-api.ts CLM-PROF

# For a claim with adverse lines (CLM-1001), stand in for the examiner in another shell:
npx tsx src/reviewer-console.ts auto
HALO=0 npx tsx src/run-raw-api.ts CLM-1001
```

Each run writes `runs/<label>.json` (tokens, turns, tool calls, **estimated cost**,
`halo_fetch` count) — the same A/B shape as the Python `run_raw_api.py`, so you can
compare the with/without-Halo arms. On the raw API the runtime does not spill large
tool results and the prefix is small, so Halo's context cut translates into real
token/cost savings that **grow with payload size** (`PROFILE_ATTACHMENTS` tunes it).

## Measured A/B (real API calls, `claude-sonnet-4-6`)

Measured on this TS runtime against the raw API, alongside the Python port for
reference. CLM-PROF auto-finalizes, so both arms run unattended:

| `get_claim` | Lang | baseline $ | halo $ | **cost saving** |
|-------------|------|-----------:|-------:|----------------:|
| ~12 KB (8 attach.)  | TypeScript | $0.167 | $0.146 | **−12%** |
| ~12 KB (8 attach.)  | Python | $0.210 | $0.189 | −10% |
| **~54 KB (40 attach.)** | TypeScript | $0.275 | $0.139 | **−49%** |
| ~54 KB (40 attach.) | Python | $0.392 | $0.206 | −48% |

Two takeaways: (1) **Halo's win scales with payload size** — ~12% on a light claim,
~49% on a heavy one — because the baseline re-sends the bulk in context every turn
while the halo arm stays flat (it fetches only `lines`, never `attachment_bodies`).
(2) **Language doesn't change the economics** — the saving percentage matches Python
closely; baseline absolute numbers vary run-to-run only because the model takes a
different number of turns (single-run variance, not a Python-vs-TS gap). Reproduce:

```bash
HALO=0 RUN_LABEL=raw_baseline npx tsx src/run-raw-api.ts CLM-PROF
HALO=1 RUN_LABEL=raw_halo     npx tsx src/run-raw-api.ts CLM-PROF
PROFILE_ATTACHMENTS=40 npx tsx db/seed.ts   # then re-run for the heavy-payload rows
```

## Layout

```
db/                     ext + agent schemas (reused .sql), 03_roles, seed.ts
src/
  engine.ts             the deterministic adjudication engine (port of engine.py)
  tools.ts              the 13 payer tools + raw Messages API tool definitions
  halo.ts               by-hand Halo encode/shape-map/fetch over @halo-format/halo
  db.ts                 pg pool (least-privilege agent role)
  prompts.ts            system prompt (CLAUDE.md) + provenance hash
  run-raw-api.ts        the manual tool-use loop (baseline + Halo arms) + --selftest
  reviewer-console.ts   the human side of the review gate
scripts/init_db.sh
CLAUDE.md               the agent's operating manual (shared with the Python example)
```

## The swap to real systems, later

You touch only the tool bodies in `src/tools.ts`: `payer_get_claim` / `_history` →
the claims platform / 837 intake; `payer_get_member_coverage` → 270/271;
`payer_post_adjudication` → 835 remittance. `adjudicateLine` (the engine) does **not**
swap — the arithmetic is never delegated to an API or a model.
