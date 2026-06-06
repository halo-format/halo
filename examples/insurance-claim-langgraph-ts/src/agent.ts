// ============================================================================
// Run the insurance-claim agent on LangGraph, with Claude (TypeScript).
//
// LangChain v1 / LangGraph: `createAgent` drives the model-calls-tools loop over
// the 15 payer tools, with `ChatAnthropic` as the model. The deterministic engine,
// the human-review gate, and the reason codes are reused unchanged.
//
//   tsx src/agent.ts CLM-PROF            # adjudicate a claim end to end
//   tsx src/agent.ts CLM-PROF --selftest # tool dispatch + engine, no API key
//   HALO=1 tsx src/agent.ts CLM-PROF     # attach the Halo LangGraph adapter (A/B)
//
// By default tools return plain JSON. HALO=1 attaches the Halo LangGraph host adapter:
// a wrapToolCall middleware encodes a large tool result (the on-demand attachment body)
// into a content-addressed store and hands the model a shape map plus a halo_fetch tool.
// ============================================================================
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { MODEL_VERSION, SYSTEM_PROMPT } from "./prompts.js";
import {
  TOOLS,
  payer_get_agent_provenance,
  payer_get_claim,
  payer_get_attachment,
  payer_adjudicate_line,
} from "./tools.js";
import { closePool } from "./db.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNS = join(__dirname, "..", "runs");
const MAX_STEPS = Number(process.env.LG_RECURSION_LIMIT || "120");

// ── Halo toggle ─────────────────────────────────────────────────────────────
const HALO_ENABLED = ["1", "true", "yes", "on"].includes((process.env.HALO || "").toLowerCase());
const HALO_THRESHOLD = Number(process.env.HALO_THRESHOLD || "2048");

const HALO_GUIDANCE = `

## Large tool results (Halo)

Some tool results come back not as the full payload but as a Halo **shape map** — a
\`[halo] map …\` note with a root kind and one line per field (ref, kind, and a bounded
preview). The full data is held, verified, out of your context.

- Read the shape map first; the previews are sized to let you decide, so most steps need
  no fetch at all.
- To read a field you still need, call \`halo_fetch(refs=[...])\` with an ARRAY of refs —
  batch every ref a step needs into ONE call (each call is a round trip). A \`[branch]\`
  ref returns its sub-refs to fetch next; every other ref returns its value.
- For an attachment body, fetch only \`narrative\` and \`findings\`. Never fetch \`image_b64\`
  — it is raw pixels you never read.
`;

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
  if (!HALO_ENABLED) return createAgent({ model, tools: TOOLS, systemPrompt: SYSTEM_PROMPT });

  const { installHalo } = await import("@halo-format/langgraph");
  const installed = installHalo({ tools: TOOLS, threshold: HALO_THRESHOLD });
  return createAgent({
    model,
    tools: installed.tools as typeof TOOLS,         // TOOLS + halo_fetch
    middleware: installed.middleware as any,        // the wrapToolCall encode middleware
    systemPrompt: SYSTEM_PROMPT + HALO_GUIDANCE,
  });
}

async function run(claimId: string): Promise<void> {
  const label = process.env.RUN_LABEL || (HALO_ENABLED ? "halo" : "baseline");
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
  const summary = { label, runtime: "langgraph_ts", halo: HALO_ENABLED, model: MODEL_VERSION, tokens: usage, total_tokens: total,
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
  const manifest = claim.attachments || [];
  console.log(`get_claim ok: ${(claim.lines || []).length} lines, ${manifest.length} attachment(s) in manifest, ${JSON.stringify(claim).length}B (light — refs + metadata, no bodies)`);

  if (manifest.length) {
    const ref = manifest[0].ref;
    const body = JSON.parse(await payer_get_attachment.invoke({ claim_id: claimId, attachment_ref: ref }));
    console.log(`get_attachment(${ref}) ok: ${JSON.stringify(body).length}B body — image_b64 ${(body.image_b64 || "").length}B (heavy — for the Halo adapter to encode)`);
  }

  const eng = JSON.parse(await payer_adjudicate_line.invoke({ claim_id: claimId, line_number: 1 }));
  console.log(`engine adjudicate_line(1): plan_paid=${eng.plan_paid_cents} review_required=${eng.review_required}`);
  console.log(`tools wired: ${TOOLS.length} LangChain tools`);

  if (HALO_ENABLED) {
    const { installHalo } = await import("@halo-format/langgraph");
    const installed = installHalo({ tools: TOOLS, threshold: HALO_THRESHOLD });
    const names = (installed.tools as any[]).map((t) => t.name);
    if (!names.includes("halo_fetch") || !installed.middleware.length) throw new Error("halo wiring incomplete");
    console.log(`halo wiring ok: +halo_fetch tool (${installed.tools.length} total), +${installed.middleware.length} middleware (HALO on)`);
  }
  console.log("== self-test OK: LangChain tools + deterministic engine functional ==");
  await closePool();
}

const argv = process.argv.slice(2);
const cid = argv.find((a) => !a.startsWith("-")) || "CLM-PROF";
(argv.includes("--selftest") ? selftest(cid) : run(cid)).catch((e) => { console.error(e); process.exit(1); });
