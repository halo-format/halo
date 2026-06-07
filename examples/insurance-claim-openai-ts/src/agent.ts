// ============================================================================
// Run the insurance-claim agent on the OpenAI Agents SDK, natively against an
// OpenAI model (TypeScript).
//
// `Runner.run` drives the model-calls-tools loop over the 15 payer tools, with an
// `Agent` configured for `gpt-4.1`. The deterministic engine, the human-review gate,
// and the reason codes are reused unchanged — only the harness is the OpenAI Agents SDK.
//
//   tsx src/agent.ts CLM-PROF            # adjudicate a claim end to end
//   tsx src/agent.ts CLM-PROF --selftest # tool dispatch + engine, no API key
//   HALO=1 tsx src/agent.ts CLM-PROF     # attach the Halo OpenAI-Agents adapter (A/B)
//
// By default tools return plain JSON. HALO=1 attaches the Halo OpenAI-Agents host adapter:
// since the released JS SDK has no call_model_input_filter, the adapter intercepts at the
// Model boundary — `wrapModelProvider` rewrites request.input before each model call, so a
// large tool result becomes a shape map (out of context) and a `halo_fetch` tool pulls back
// only the fields the model needs. OpenAI caches the prompt prefix automatically, so there
// is no separate CACHE toggle in this port.
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
const MAX_STEPS = Number(process.env.MAX_TURNS || "120");

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

// OpenAI per-MTok pricing (USD). `cached` is the discounted rate for the cached prompt
// prefix — OpenAI caches automatically, with no write premium (unlike Anthropic).
const PRICING: Record<string, { in: number; out: number; cached: number }> = {
  "gpt-4.1": { in: 2.0, out: 8.0, cached: 0.5 },
  "gpt-4.1-mini": { in: 0.4, out: 1.6, cached: 0.1 },
  "gpt-4o": { in: 2.5, out: 10.0, cached: 1.25 },
  "gpt-5": { in: 1.25, out: 10.0, cached: 0.125 },
};
function cost(u: Record<string, number>, model: string): number | null {
  const p = PRICING[model];
  if (!p) return null;
  const m = 1_000_000;
  const fresh = Math.max(0, (u.input_tokens || 0) - (u.cached_tokens || 0));
  return Number(((fresh * p.in + (u.cached_tokens || 0) * p.cached + (u.output_tokens || 0) * p.out) / m).toFixed(6));
}

// Aggregate token usage from the run's raw model responses (the public, stable path), and
// count tool calls from the run items.
function meter(result: any): { usage: Record<string, number>; total: number; tools: Record<string, number> } {
  let input = 0, output = 0, cached = 0;
  for (const r of result.rawResponses || []) {
    const u = r.usage || {};
    input += u.inputTokens || 0;
    output += u.outputTokens || 0;
    for (const d of u.inputTokensDetails || []) cached += d.cached_tokens || d.cachedTokens || 0;
  }
  const tools: Record<string, number> = {};
  for (const it of result.newItems || []) {
    if (it.type === "tool_call_item") {
      const name = it.rawItem?.name || "?";
      tools[name] = (tools[name] || 0) + 1;
    }
  }
  const usage = { input_tokens: input, cached_tokens: cached, output_tokens: output };
  return { usage, total: input + output, tools };
}

async function buildRunner(): Promise<{ agent: any; runner: any; prompt: (id: string) => string }> {
  const { Agent, Runner, OpenAIProvider } = await import("@openai/agents");

  let tools: any[] = TOOLS;
  let instructions = SYSTEM_PROMPT;
  let runner: any = new Runner();

  if (HALO_ENABLED) {
    const { installHalo } = await import("@halo-format/openai");
    const installed = installHalo({ tools: TOOLS, threshold: HALO_THRESHOLD });
    tools = installed.tools as any[]; // TOOLS + halo_fetch
    instructions = SYSTEM_PROMPT + HALO_GUIDANCE;
    // The agent names its model by string, so wrap the provider that resolves it — every model
    // it returns rewrites request.input (the encode seam) before the model call.
    runner = new Runner({ modelProvider: installed.wrapModelProvider(new OpenAIProvider()) });
  }

  const agent = new Agent({ name: "insurance-claim-decision-agent", instructions, tools, model: MODEL_VERSION });
  const prompt = (claimId: string) =>
    `Adjudicate insurance claim ${claimId} end to end: decide each service line ` +
    `(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, record the ` +
    `decisions, open the review gate and wait for the examiner if required, then post the adjudication. ` +
    `Finish with a one-line per-line summary.`;
  return { agent, runner, prompt };
}

async function run(claimId: string): Promise<void> {
  const label = process.env.RUN_LABEL || (HALO_ENABLED ? "halo" : "baseline");
  const { agent, runner, prompt } = await buildRunner();
  console.log(`=== Insurance Claim Decision Agent — OpenAI Agents SDK (TS) — ${claimId} (model ${MODEL_VERSION}) ===\n`);

  const result = await runner.run(agent, prompt(claimId), { maxTurns: MAX_STEPS });
  const { usage, total, tools } = meter(result);
  console.log(typeof result.finalOutput === "string" ? result.finalOutput : JSON.stringify(result.finalOutput));

  const summary = { label, runtime: "openai_agents_ts", halo: HALO_ENABLED, model: MODEL_VERSION, tokens: usage,
    total_tokens: total, estimated_cost_usd: cost(usage, MODEL_VERSION), tool_calls: tools,
    tool_call_total: Object.values(tools).reduce((a, b) => a + b, 0) };
  mkdirSync(RUNS, { recursive: true });
  writeFileSync(join(RUNS, `${label}.json`), JSON.stringify(summary, null, 2));
  console.log(`\n=== ${label} === tokens=${total.toLocaleString()} cost=$${summary.estimated_cost_usd} tool_calls=${summary.tool_call_total}`);
  console.log(`(written to runs/${label}.json)`);
  await closePool();
}

async function selftest(claimId: string): Promise<void> {
  console.log("== OpenAI Agents self-test (no API call) ==");
  const prov = JSON.parse(await payer_get_agent_provenance());
  console.log("provenance tool ok:", prov.agent_id);

  const claim = JSON.parse(await payer_get_claim({ claim_id: claimId }));
  const manifest = claim.attachments || [];
  console.log(`get_claim ok: ${(claim.lines || []).length} lines, ${manifest.length} attachment(s) in manifest, ${JSON.stringify(claim).length}B (light — refs + metadata, no bodies)`);

  if (manifest.length) {
    const ref = manifest[0].ref;
    const body = JSON.parse(await payer_get_attachment({ claim_id: claimId, attachment_ref: ref }));
    console.log(`get_attachment(${ref}) ok: ${JSON.stringify(body).length}B body — image_b64 ${(body.image_b64 || "").length}B (heavy — for the Halo adapter to encode)`);
  }

  const eng = JSON.parse(await payer_adjudicate_line({ claim_id: claimId, line_number: 1 }));
  console.log(`engine adjudicate_line(1): plan_paid=${eng.plan_paid_cents} review_required=${eng.review_required}`);
  console.log(`tools wired: ${TOOLS.length} function tools`);

  if (HALO_ENABLED) {
    const { installHalo } = await import("@halo-format/openai");
    const installed = installHalo({ tools: TOOLS, threshold: HALO_THRESHOLD });
    const names = (installed.tools as any[]).map((t) => t.name);
    if (!names.includes("halo_fetch") || typeof installed.wrapModelProvider !== "function") throw new Error("halo wiring incomplete");
    console.log(`halo wiring ok: +halo_fetch tool (${installed.tools.length} total), +wrapModelProvider (HALO on)`);
  }
  console.log("== self-test OK: function tools + deterministic engine functional ==");
  await closePool();
}

const argv = process.argv.slice(2);
const cid = argv.find((a) => !a.startsWith("-")) || "CLM-PROF";
(argv.includes("--selftest") ? selftest(cid) : run(cid)).catch((e) => { console.error(e); process.exit(1); });
