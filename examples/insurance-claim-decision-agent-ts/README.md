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
verbatim), the same deterministic engine, the same normalized tools (claim manifest
+ on-demand attachment bodies), the same human-review gate, and the same seeded
claims. Evidence handles are computed with the published `@halo-format/halo` core,
so they're **byte-identical to the Python port**.

## The tool-use loop (raw API)

`src/run-raw-api.ts` is a manual loop:

```
messages.create({ system, tools, messages })
  → if stop_reason === "tool_use": run each tool in-process, append tool_result, repeat
  → else: done
```

The payer tools are declared as raw tool definitions (`src/tools.ts` → `TOOL_DEFS`)
and dispatched to the same functions that hold the SQL. They are normalized like a
real payer/X12 API — `payer_get_claim` returns an attachment **manifest** (refs +
metadata), and a clinical **body** is fetched with `payer_get_attachment` only when
a line needs documentation review. With **`HALO=1`**, a large tool result is encoded
into a Halo store *by hand* (the raw API has no hook) via the published
`@halo-format/claude/raw` adapter, the model is handed the **shape map** instead of
the payload, and a `halo_fetch` tool pulls back only the fields it needs (verified
on read).

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

# 4b. The agent, raw API. CLM-BIG (2 crowns → documentation review) and CLM-1001 hit
#     the review gate, so stand in for the examiner in another shell:
npx tsx src/reviewer-console.ts auto
HALO=0 RUN_LABEL=raw_baseline npx tsx src/run-raw-api.ts CLM-BIG
HALO=1 RUN_LABEL=raw_halo     npx tsx src/run-raw-api.ts CLM-BIG
```

Each run writes `runs/<label>.json` (tokens, turns, tool calls, **estimated cost**,
`halo_fetch` count) — the same A/B shape as the Python `run_raw_api.py`, so you can
compare the with/without-Halo arms. With the normalized tools, the large results are
the **attachment bodies** the agent opens for documentation review; both arms fetch
the same bodies, and Halo slices each to `narrative`+`findings`, skipping the raw
`image_b64`.

## Measured A/B (real API calls, `claude-sonnet-4-6`)

The documentation-heavy claim **CLM-BIG** (exam + 2 crowns → 2 attachment bodies
opened), measured on this TS runtime, alongside the Python port for reference
(single runs; a live agent is non-deterministic):

| Claim | Lang | baseline tokens | halo tokens | **token saving** | baseline $ | halo $ | **cost saving** |
|-------|------|----------------:|------------:|-----------------:|-----------:|-------:|----------------:|
| CLM-BIG | **TypeScript** | 611,974 | 122,182 | **−80%** | $0.914 | $0.210 | **−77%** |
| CLM-BIG | Python | 678,445 | 150,085 | −78% | $0.853 | $0.264 | −69% |

Two takeaways: (1) **the win scales with the attachment bodies the agent opens** —
the baseline re-sends each opened body's raw image bytes in context every turn,
while the halo arm pulls only the narrative/findings it reads and keeps the
un-reviewed attachments out entirely, so it stays flat. The result is honest:
nothing is force-fed to the baseline; both arms fetch the same bodies and Halo
navigates within them. (2) **Language doesn't change the economics** — TS and Python
land within run-to-run variance of each other. Reproduce:

```bash
npx tsx src/reviewer-console.ts auto &          # CLM-BIG hits the review gate
HALO=0 RUN_LABEL=raw_baseline npx tsx src/run-raw-api.ts CLM-BIG
HALO=1 RUN_LABEL=raw_halo     npx tsx src/run-raw-api.ts CLM-BIG
BIG_ATTACHMENTS=30 npx tsx db/seed.ts           # widen the gap with more/larger bodies
```

## Layout

```
db/                     ext + agent schemas (reused .sql), 03_roles, seed.ts
src/
  engine.ts             the deterministic adjudication engine (port of engine.py)
  tools.ts              the payer tools + raw Messages API tool definitions
                        (get_claim manifest + get_attachment bodies)
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
