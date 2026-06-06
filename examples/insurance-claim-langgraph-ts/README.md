# Insurance Claim Decision Agent — LangGraph (TypeScript)

A **LangGraph** port of the insurance-claim-decision-agent in TypeScript. It uses
`createAgent` from LangChain v1 (built on LangGraph) with **Claude** via
`ChatAnthropic` (`@langchain/anthropic`), over the **same deterministic engine,
schema, and human-review gate** as the other ports. Only the agent harness changes.

> **No Halo here on purpose.** The tools return plain JSON; this is the clean agent
> the **Halo LangGraph host adapter** attaches to. `payer_get_claim` still returns
> the heavy claim (header + lines + bulky attachment bodies) so there's a real
> payload for that adapter to encode.

## How it's wired

```typescript
import { createAgent } from "langchain";
import { ChatAnthropic } from "@langchain/anthropic";
import { TOOLS } from "./tools.js";            // 13 payer tools as tool() + zod

const model = new ChatAnthropic({ model: "claude-sonnet-4-6", maxTokens: 8000 });
const agent = createAgent({ model, tools: TOOLS, systemPrompt: SYSTEM_PROMPT }); // SYSTEM_PROMPT = CLAUDE.md
const result = await agent.invoke(
  { messages: [{ role: "user", content: prompt }] },
  { recursionLimit: 120 },
);
```

The 13 tools (`src/tools.ts`) are `tool()` functions with zod schemas wrapping the
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

## Where Halo plugs in (for you)

The Halo LangGraph adapter wraps this agent at the **tool-result boundary** — encode
a large `ToolMessage` into a content-addressed store, hand the model a shape map, and
expose a `halo_fetch` tool — without touching the engine, the gate, or the decision
logic here. The `agent.halo_nodes` / `agent.halo_maps` tables are already in the
schema for it to use.

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
