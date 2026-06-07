# Insurance Claim Decision Agent — OpenAI Agents SDK (TypeScript)

An **OpenAI Agents SDK** port of the insurance-claim-decision-agent. It uses a native
`Agent` + `Runner` loop against **`gpt-4.1`**, over the **same deterministic engine, schema,
and human-review gate** as the other ports. Only the agent harness changes.

> **Halo is opt-in (`HALO=1`).** By default the tools return plain JSON — the clean baseline.
> `HALO=1` attaches the **Halo OpenAI-Agents host adapter** (it keeps large tool results out of
> the model's context and records content-addressed evidence), for an A/B. The heavy payload is
> the on-demand attachment body from `payer_get_attachment` — narrative/findings plus a bulky
> `image_b64` blob — which is the real payload that adapter encodes.

## How it's wired

```ts
import { Agent, Runner } from "@openai/agents";
import { TOOLS } from "./tools.js";            // 15 payer tools as function tools

const agent = new Agent({ name: "insurance-claim-decision-agent",
  instructions: SYSTEM_PROMPT, tools: TOOLS, model: "gpt-4.1" });
const result = await new Runner().run(agent, prompt, { maxTurns: 120 });
```

The 15 tools (`src/tools.ts`) are the SDK's `tool()` over plain JSON-schema parameters (so the
example needs no zod); each wraps the SQL on `ext.*`/`agent.*`. `payer_adjudicate_line` runs
the deterministic engine (`src/engine.ts`); `payer_request_review` blocks on the
`agent.approvals` gate; `payer_post_adjudication` writes the 835/EOB.

## Quick start

```bash
# 1. Postgres (database mimic_payer — shared with the other examples)
#    docker compose up -d   (see ../insurance-claim-decision-agent)

# 2. Deps + config
npm install
cp .env.example .env              # set OPENAI_API_KEY, DB DSN

# 3. Schema + agent role + seed
set -a && . ./.env && set +a
npm run initdb && npm run seed

# 4a. No-API-key smoke test (tools + engine)
npm run agent -- CLM-PROF --selftest

# 4b. The agent (CLM-PROF auto-finalizes; CLM-1001 needs the examiner)
npm run agent -- CLM-PROF
#   for CLM-1001, in another shell: npm run reviewer -- auto
```

Each run writes `runs/<label>.json` (token usage from the raw model responses, estimated cost,
per-tool counts).

## Halo A/B (`HALO=1`)

```bash
HALO=1 npm run agent -- CLM-PROF          # Halo on  -> runs/halo.json
npm run agent -- CLM-PROF                 # baseline -> runs/baseline.json
```

`HALO=1` calls `installHalo({ tools: TOOLS })`, appends `halo_fetch` to the tools, and wraps
the model provider so a large tool result becomes a shape map before the model sees it.
Navigation guidance rides in the instructions (prompt mode). Tune the encode floor with
`HALO_THRESHOLD` (default 2048).

> **The interception seam, and why it differs from the Python port.** The Python `openai-agents`
> SDK exposes `RunConfig.call_model_input_filter`; the released JS `@openai/agents` (0.1.x) does
> **not**. So the TS adapter intercepts one layer down, at the `Model` boundary —
> `wrapModelProvider` rewrites `request.input` before each model call. Same point in the pipeline
> (right before the model call), same generic reach (every tool's output flows through the model
> request). OpenAI caches the prompt prefix automatically, so there is no `CACHE` toggle here.

### Where Halo wins

The reliable, deterministic win is the **per-payload context reduction**: when the model needs a
few small fields out of a large result, the blob never enters context. The self-contained
`scripts/ab-big-payload.ts` isolates it (one ~200KB attachment, a question answerable from the
small fields — only an API key, no DB):

```bash
npm run ab          # baseline vs halo on one big payload
```

Across a *long* adjudication loop with *modest* payloads it is closer to a wash — Halo's extra
`halo_fetch` round trips can offset the small blobs they remove, and OpenAI's automatic prefix
caching makes a carried blob cheap to re-read. Halo dominates when the payload is large relative
to the conversation. The core engine is
[`@halo-format/openai`](https://www.npmjs.com/package/@halo-format/openai).

## Layout

```
src/
  agent.ts     Agent + Runner runner + HALO toggle + token meter + --selftest
  tools.ts     the 15 payer tools as function tools (JSON-schema params, no zod)
  engine.ts    the deterministic adjudication engine (shared, no LLM)
  prompts.ts   system prompt (CLAUDE.md) + provenance hash
  db.ts        pg pool (least-privilege agent role)
  reviewer-console.ts   the human examiner CLI
db/            ext + agent schemas, role/grants, seed
scripts/       init_db.sh, ab-big-payload.ts
CLAUDE.md      the agent's operating manual (shared with the other ports)
```
