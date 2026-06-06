// ============================================================================
// Run the insurance-claim agent on LangGraph, with Claude (TypeScript).
//
// LangChain v1 / LangGraph: `createAgent` drives the model-calls-tools loop over
// the 13 payer tools, with `ChatAnthropic` as the model. The deterministic engine,
// the human-review gate, and the reason codes are reused unchanged.
//
//   tsx src/agent.ts CLM-PROF            # adjudicate a claim end to end
//   tsx src/agent.ts CLM-PROF --selftest # tool dispatch + engine, no API key
//
// Ships WITHOUT a Halo integration — tools return plain JSON. The Halo LangGraph
// host adapter attaches separately; this is the clean agent it wraps.
// ============================================================================
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { MODEL_VERSION, SYSTEM_PROMPT } from "./prompts.js";
import { TOOLS, payer_get_agent_provenance, payer_get_claim, payer_adjudicate_line } from "./tools.js";
import { closePool } from "./db.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNS = join(__dirname, "..", "runs");
const MAX_STEPS = Number(process.env.LG_RECURSION_LIMIT || "120");

const PRICING: Record<string, { in: number; out: number; cr: number; cw: number }> = {
  "claude-opus-4-8": { in: 5, out: 25, cr: 0.5, cw: 6.25 },
  "claude-sonnet-4-6": { in: 3, out: 15, cr: 0.3, cw: 3.75 },
  "claude-haiku-4-5": { in: 1, out: 5, cr: 0.1, cw: 1.25 },
};
function cost(u: Record<string, number>, model: string): number | null {
  const p = PRICING[model];
  if (!p) return null;
  const m = 1_000_000;
  return Number((((u.input_tokens || 0) * p.in + (u.output_tokens || 0) * p.out + (u.cache_read || 0) * p.cr + (u.cache_creation || 0) * p.cw) / m).toFixed(6));
}

async function buildAgent() {
  const { createAgent } = await import("langchain");
  const { ChatAnthropic } = await import("@langchain/anthropic");
  const model = new ChatAnthropic({ model: MODEL_VERSION, maxTokens: 8000 });
  return createAgent({ model, tools: TOOLS, systemPrompt: SYSTEM_PROMPT });
}

async function run(claimId: string): Promise<void> {
  const label = process.env.RUN_LABEL || "langgraph_ts";
  const agent = await buildAgent();
  const prompt =
    `Adjudicate insurance claim ${claimId} end to end: decide each service line ` +
    `(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, record the ` +
    `decisions, open the review gate and wait for the examiner if required, then post the adjudication. ` +
    `Finish with a one-line per-line summary.`;
  console.log(`=== Insurance Claim Decision Agent — LangGraph + Claude (TS) — ${claimId} (model ${MODEL_VERSION}) ===\n`);

  const result: any = await agent.invoke(
    { messages: [{ role: "user", content: prompt }] },
    { recursionLimit: MAX_STEPS },
  );

  const usage: Record<string, number> = {};
  const tools: Record<string, number> = {};
  for (const msg of result.messages) {
    const um = msg.usage_metadata;
    if (um) {
      usage.input_tokens = (usage.input_tokens || 0) + (um.input_tokens || 0);
      usage.output_tokens = (usage.output_tokens || 0) + (um.output_tokens || 0);
      const det = um.input_token_details || {};
      usage.cache_read = (usage.cache_read || 0) + (det.cache_read || 0);
      usage.cache_creation = (usage.cache_creation || 0) + (det.cache_creation || 0);
    }
    for (const tc of msg.tool_calls || []) tools[tc.name] = (tools[tc.name] || 0) + 1;
  }
  const last = result.messages[result.messages.length - 1];
  console.log(typeof last.content === "string" ? last.content : JSON.stringify(last.content));

  const total = Object.values(usage).reduce((a, b) => a + b, 0);
  const summary = { label, runtime: "langgraph_ts", model: MODEL_VERSION, tokens: usage, total_tokens: total,
    estimated_cost_usd: cost(usage, MODEL_VERSION), tool_calls: tools, tool_call_total: Object.values(tools).reduce((a, b) => a + b, 0) };
  mkdirSync(RUNS, { recursive: true });
  writeFileSync(join(RUNS, `${label}.json`), JSON.stringify(summary, null, 2));
  console.log(`\n=== ${label} === tokens=${total.toLocaleString()} cost=$${summary.estimated_cost_usd} tool_calls=${summary.tool_call_total}`);
  console.log(`(written to runs/${label}.json)`);
  await closePool();
}

async function selftest(claimId: string): Promise<void> {
  console.log("== LangGraph self-test (no API call) ==");
  const prov = JSON.parse(await payer_get_agent_provenance.invoke({}));
  console.log("provenance tool ok:", prov.agent_id);
  const claim = JSON.parse(await payer_get_claim.invoke({ claim_id: claimId }));
  console.log(`get_claim ok: ${(claim.lines || []).length} lines, ${JSON.stringify(claim).length}B payload (heavy — for the Halo adapter to encode)`);
  const eng = JSON.parse(await payer_adjudicate_line.invoke({ claim_id: claimId, line_number: 1 }));
  console.log(`engine adjudicate_line(1): plan_paid=${eng.plan_paid_cents} review_required=${eng.review_required}`);
  console.log(`tools wired: ${TOOLS.length} LangChain tools`);
  console.log("== self-test OK: LangChain tools + deterministic engine functional ==");
  await closePool();
}

const argv = process.argv.slice(2);
const cid = argv.find((a) => !a.startsWith("-")) || "CLM-PROF";
(argv.includes("--selftest") ? selftest(cid) : run(cid)).catch((e) => { console.error(e); process.exit(1); });
