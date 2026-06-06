# Insurance Claim Decision Agent — LangGraph (TypeScript)

A **LangGraph** port of the insurance-claim-decision-agent in TypeScript. It uses
`createAgent` from LangChain v1 (built on LangGraph) with **Claude** via
`ChatAnthropic` (`@langchain/anthropic`), over the **same deterministic engine,
schema, and human-review gate** as the other ports. Only the agent harness changes.

> **Halo is opt-in (`HALO=1`).** By default the tools return plain JSON — this is the
> clean baseline. `HALO=1` attaches the **Halo LangGraph host adapter** for an A/B. The
> claim API is REST-normalized: `payer_get_claim` returns a light attachment **manifest**,
> and the heavy clinical body — narrative/findings plus a bulky `image_b64` blob — is
> fetched on demand with `payer_get_attachment`, which is the real payload that adapter
> encodes. See [Halo A/B](#halo-ab-halo1).

## How it's wired

```typescript
import { createAgent } from "langchain";
import { ChatAnthropic } from "@langchain/anthropic";
import { installHalo } from "@halo-format/langgraph";
import { TOOLS } from "./tools.js";            // 15 payer tools as tool() + zod

const model = new ChatAnthropic({ model: "claude-sonnet-4-6", maxTokens: 8000 });

// baseline:
const agent = createAgent({ model, tools: TOOLS, systemPrompt: SYSTEM_PROMPT });

// HALO=1: append halo_fetch + the encode middleware
const halo = installHalo({ tools: TOOLS });
const haloAgent = createAgent({ model, tools: halo.tools, middleware: halo.middleware, systemPrompt: SYSTEM_PROMPT + HALO_GUIDANCE });
```

The 15 tools (`src/tools.ts`) are `tool()` functions with zod schemas wrapping the
SQL on `ext.*`/`agent.*`. `payer_adjudicate_line` runs the deterministic engine
(`src/engine.ts`); `payer_request_review` blocks on the `agent.approvals` gate;
`payer_post_adjudication` writes the 835/EOB.

## Quick start

```bash
# 1. Postgres (database mimic_payer — shared with the other examples)
npm install
cp .env.example .env                # set ANTHROPIC_API_KEY, DB DSN
set -a && . ./.env && set +a
bash scripts/init_db.sh

# 2a. No-API-key smoke test (tools + engine)
npx tsx src/agent.ts CLM-PROF --selftest

# 2b. The agent (CLM-PROF auto-finalizes; CLM-1001 needs the examiner)
npx tsx src/agent.ts CLM-PROF
#   for CLM-1001, in another shell: npx tsx src/reviewer-console.ts auto
```

Each run writes `runs/<label>.json` (token usage from the message stream, estimated
cost, per-tool counts).

## Halo A/B (`HALO=1`)

The Halo LangGraph adapter wraps this agent at the **tool-result boundary** — a
`wrapToolCall` middleware encodes a large `ToolMessage` into a content-addressed store,
hands the model a shape map, and exposes a `halo_fetch` tool — without touching the
engine, the gate, or the decision logic here.

```bash
HALO=1 npx tsx src/agent.ts CLM-PROF          # Halo on  -> runs/halo.json
npx tsx src/agent.ts CLM-PROF                 # baseline -> runs/baseline.json
```

`HALO=1` calls `installHalo({ tools: TOOLS })`, appends `halo_fetch` and the encode
middleware to `createAgent`, and rides navigation guidance in the system prompt. The
payload it earns its keep on is the **on-demand attachment body** from
`payer_get_attachment`. Tune the encode floor with `HALO_THRESHOLD` (default 2048
bytes). Compare the two `runs/*.json` for the per-payload context reduction.

## Layout

```
src/
  agent.ts     createAgent runner (LangGraph) + token meter + --selftest
  tools.ts     the 13 payer tools as LangChain tool() + zod
  engine.ts    the deterministic adjudication engine (shared, no LLM)
  prompts.ts   system prompt (CLAUDE.md) + provenance hash
  db.ts        pg pool (least-privilege agent role)
db/            ext + agent schemas, role/grants, seed.ts
scripts/       init_db.sh
CLAUDE.md      the agent's operating manual (shared with the other ports)
```
