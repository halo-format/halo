// ============================================================================
// Run the insurance-claim agent against the RAW Claude Messages API in TypeScript.
//
// A manual agentic loop on anthropic.messages.create with the 13 payer tools as
// raw tool definitions, dispatched in-process to the same tool functions. The
// deterministic engine, the human-review gate, the evidence store, and the reason
// codes are reused unchanged — only the runtime differs. This is the TS twin of
// the Python scripts/run_raw_api.py.
//
//   HALO=0 RUN_LABEL=raw_baseline tsx src/run-raw-api.ts CLM-PROF
//   HALO=1 RUN_LABEL=raw_halo     tsx src/run-raw-api.ts CLM-PROF
//
// With HALO=1 a large tool result is encoded (by hand — the raw API has no hook)
// into a Halo store; the model sees the shape map and pulls fields with halo_fetch.
// The encode/fetch mechanism is the published adapter's raw-Messages-API surface
// (@halo-format/claude/raw — createRawHalo), the same engine the Agent SDK path drives
// via a hook, so this example carries no Halo code of its own.
// --selftest exercises tool dispatch + Halo encode/fetch with no API call.
// ============================================================================
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createRawHalo, type RawHalo } from "@halo-format/claude/raw";
import { MODEL_VERSION, SYSTEM_PROMPT } from "./prompts.js";
import { DISPATCH, TOOL_DEFS } from "./tools.js";
import { closePool } from "./db.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNS = join(__dirname, "..", "runs");
const HALO = ["1", "true", "yes", "on"].includes((process.env.HALO || "").toLowerCase());
const THRESHOLD = Number(process.env.HALO_THRESHOLD || "2048");
const MAX_TURNS = Number(process.env.RAW_MAX_TURNS || "40");

const PRICING: Record<string, { in: number; out: number; cr: number; cw: number }> = {
  "claude-opus-4-8": { in: 5, out: 25, cr: 0.5, cw: 6.25 },
  "claude-sonnet-4-6": { in: 3, out: 15, cr: 0.3, cw: 3.75 },
  "claude-haiku-4-5": { in: 1, out: 5, cr: 0.1, cw: 1.25 },
};

// A one-line domain hint appended to the package's generic navigation guidance.
const DOMAIN_HINT =
  "\nFor a claim, fetch the service `lines` from the map. For a line needing documentation review " +
  "(major restorative, endodontic, periodontal, oral surgery), call payer_get_attachment for its " +
  "supporting attachment and read ONLY `narrative` and `findings` — never fetch `image_b64` (raw " +
  "pixels: large and unreadable). Routine preventive/basic lines need no attachment.";

function buildTools(haloDef?: unknown): any[] {
  const defs: any[] = [...TOOL_DEFS, ...(haloDef ? [haloDef] : [])];
  // cache tools + system together (prompt caching).
  defs[defs.length - 1] = { ...defs[defs.length - 1], cache_control: { type: "ephemeral" } };
  return defs;
}

async function execute(name: string, args: any, halo: RawHalo | null): Promise<string> {
  if (halo && halo.isFetch(name)) return halo.fetch(args.refs); // verified leaves; never re-encode
  const result = await DISPATCH[name](args);
  return halo ? halo.encodeResult(name, args, result) : JSON.stringify(result);
}

function cost(u: Record<string, number>, model: string): number | null {
  const p = PRICING[model];
  if (!p) return null;
  const m = 1_000_000;
  return Number(
    ((u.input_tokens || 0) * p.in / m + (u.output_tokens || 0) * p.out / m +
      (u.cache_read_input_tokens || 0) * p.cr / m + (u.cache_creation_input_tokens || 0) * p.cw / m).toFixed(6),
  );
}

async function run(claimId: string): Promise<void> {
  const { default: Anthropic } = await import("@anthropic-ai/sdk");
  const client = new Anthropic();
  const label = process.env.RUN_LABEL || (HALO ? "raw_halo" : "raw_baseline");
  const halo: RawHalo | null = HALO ? createRawHalo({ threshold: THRESHOLD }) : null;

  const system = [{ type: "text" as const, text: SYSTEM_PROMPT + (halo ? halo.guidance + DOMAIN_HINT : ""), cache_control: { type: "ephemeral" as const } }];
  const tools = buildTools(halo?.toolDef);
  const prompt =
    `Adjudicate insurance claim ${claimId} end to end: decide each service line ` +
    `(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, record the ` +
    `decisions with evidence, open the review gate and wait for the examiner if required, then post ` +
    `the adjudication. Finish with a one-line per-line summary.`;
  const messages: any[] = [{ role: "user", content: prompt }];

  const usage: Record<string, number> = {};
  const toolCalls: Record<string, number> = {};
  let turns = 0;

  console.log(`=== Insurance Claim Decision Agent — RAW Claude API (TS) — ${claimId} — ${HALO ? "HALO" : "BASELINE"} (model ${MODEL_VERSION}) ===\n`);

  while (turns < MAX_TURNS) {
    turns++;
    const resp: any = await client.messages.create({ model: MODEL_VERSION, max_tokens: 8000, system, tools, messages });
    for (const k of ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"])
      usage[k] = (usage[k] || 0) + (resp.usage?.[k] || 0);

    for (const block of resp.content) {
      if (block.type === "text" && block.text.trim()) console.log(block.text);
      else if (block.type === "tool_use") {
        toolCalls[block.name] = (toolCalls[block.name] || 0) + 1;
        console.log(`  → ${block.name} ${JSON.stringify(block.input).slice(0, 120)}`);
      }
    }
    messages.push({ role: "assistant", content: resp.content });
    if (resp.stop_reason !== "tool_use") break;

    const results: any[] = [];
    for (const block of resp.content) {
      if (block.type === "tool_use") {
        try {
          results.push({ type: "tool_result", tool_use_id: block.id, content: await execute(block.name, block.input, halo) });
        } catch (e: any) {
          results.push({ type: "tool_result", tool_use_id: block.id, content: `error: ${e?.message ?? e}`, is_error: true });
        }
      }
    }
    messages.push({ role: "user", content: results });
  }

  const total = Object.values(usage).reduce((a, b) => a + b, 0);
  const summary = {
    label, runtime: "raw_messages_api_ts", halo_enabled: HALO, model: MODEL_VERSION,
    tokens: usage, total_tokens: total, estimated_cost_usd: cost(usage, MODEL_VERSION),
    turns, tool_calls: toolCalls, halo_fetch_calls: toolCalls["halo_fetch"] || 0,
  };
  mkdirSync(RUNS, { recursive: true });
  writeFileSync(join(RUNS, `${label}.json`), JSON.stringify(summary, null, 2));
  console.log(`\n=== ${label} === tokens=${total.toLocaleString()} cost=$${summary.estimated_cost_usd} turns=${turns} tool_calls=${Object.values(toolCalls).reduce((a, b) => a + b, 0)} halo_fetch=${summary.halo_fetch_calls}`);
  console.log(`(written to runs/${label}.json)`);
  await closePool();
}

async function selftest(claimId: string): Promise<void> {
  console.log("== TS raw-api self-test (no API call) ==");
  const prov = await DISPATCH.payer_get_agent_provenance({});
  console.log("provenance tool ok:", prov.agent_id);
  const halo = createRawHalo({ threshold: THRESHOLD });
  const claim = await DISPATCH.payer_get_claim({ claim_id: claimId });
  const full = JSON.stringify(claim);
  const shape = await halo.encodeResult("payer_get_claim", { claim_id: claimId }, claim);
  console.log(`get_claim: full=${full.length}B  shape_map_model_sees=${shape.length}B  (${Math.round(100 * (1 - shape.length / full.length))}% smaller)`);
  const fetched: any = JSON.parse(await halo.fetch([`${claimId}.lines`]));
  const ref = `${claimId}.lines`;
  console.log(`halo_fetch(['${ref}']) verified ok: ${fetched[ref].ok && Array.isArray(fetched[ref].value)} (${fetched[ref].value?.length} lines)`);
  const eng = await DISPATCH.payer_adjudicate_line({ claim_id: claimId, line_number: 1 });
  console.log(`engine adjudicate_line(1): plan_paid=${eng.plan_paid_cents} review_required=${eng.review_required}`);
  console.log(`tools wired: ${TOOL_DEFS.length} domain tools + halo_fetch`);
  console.log("== self-test OK: tool dispatch + Halo encode/fetch all functional ==");
  await closePool();
}

const argv = process.argv.slice(2);
const cid = argv.find((a) => !a.startsWith("-")) || "CLM-PROF";
(argv.includes("--selftest") ? selftest(cid) : run(cid)).catch((e) => {
  console.error(e);
  process.exit(1);
});
