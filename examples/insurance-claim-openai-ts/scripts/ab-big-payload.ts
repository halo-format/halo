// ============================================================================
// Big-payload A/B: baseline (raw JSON) vs Halo, on one large attachment body (TS).
//
// Self-contained — needs only OPENAI_API_KEY (no database, no review gate). It builds a
// single get_attachment tool returning a realistic large dental attachment (small clinical
// fields + a ~200KB raw image_b64 blob), then asks a question answerable from the small
// fields alone, and runs the task twice:
//
//   baseline — the tool result lands in context whole; the 200KB blob is in the prompt.
//   halo     — installHalo wraps the model; the model sees a shape map and halo_fetches only
//              kind/findings, so the blob never enters context.
//
// This isolates Halo's per-payload context reduction (the reliable win) from conversation
// length. OpenAI caches the prompt prefix automatically, so a re-read blob is cheaper than
// full price but never free.
//
//   tsx scripts/ab-big-payload.ts          # default ~200KB image
//   IMAGE_KB=400 tsx scripts/ab-big-payload.ts
// ============================================================================
import { createHash } from "node:crypto";

const MODEL = process.env.AGENT_MODEL || "gpt-4.1";
const IMAGE_KB = Number(process.env.IMAGE_KB || "200");
const PRICE = { in: 2.0, out: 8.0, cached: 0.5 }; // gpt-4.1 per-MTok

const HALO_GUIDANCE =
  "Large tool results come back as a Halo shape map (a `[halo] map …` note with one line per " +
  "field: ref, kind, preview). Read the previews; for a field you still need call " +
  "halo_fetch(refs=[...]) with an ARRAY of refs (batch them). Never fetch `image_b64`.";

const TASK =
  "Fetch attachment ATT-BIG-02 and tell me: its kind, and whether its findings support a crown " +
  "on tooth #19. Do not read or echo the image_b64 field. Answer in one sentence.";

function attachmentBody(): Record<string, unknown> {
  const unit = createHash("sha256").update("CLM-BIG/ATT-BIG-02/image").digest("base64");
  const imageB64 = unit.repeat(Math.ceil((IMAGE_KB * 1024) / unit.length)).slice(0, IMAGE_KB * 1024);
  const chart: Record<string, string> = {};
  for (let t = 1; t <= 32; t++) chart[t] = "sound";
  return {
    attachment_ref: "ATT-BIG-02", claim_id: "CLM-BIG", kind: "periapical_xray", captured_at: "2026-05-18",
    narrative: "Patient presents for crown prep on tooth #19. Deep restoration with recurrent decay.",
    findings: "Deep carious lesion approximating the pulp; crown indicated to restore the tooth.",
    tooth_chart: chart,
    image_meta: { dpi: 300, bytes: IMAGE_KB * 1024, modality: "intraoral" },
    image_b64: imageB64, // raw pixels — large, not human-readable
  };
}

const DOC = attachmentBody();

function meter(result: any): { input: number; cached: number; output: number; calls: number; answer: string } {
  let input = 0, output = 0, cached = 0;
  for (const r of result.rawResponses || []) {
    const u = r.usage || {};
    input += u.inputTokens || 0;
    output += u.outputTokens || 0;
    for (const d of u.inputTokensDetails || []) cached += d.cached_tokens || d.cachedTokens || 0;
  }
  const calls = (result.newItems || []).filter((it: any) => it.type === "tool_call_item").length;
  return { input, cached, output, calls, answer: (typeof result.finalOutput === "string" ? result.finalOutput : JSON.stringify(result.finalOutput) || "").trim() };
}

const cost = (r: { input: number; cached: number; output: number }) => {
  const m = 1_000_000;
  const fresh = Math.max(0, r.input - r.cached);
  return (fresh * PRICE.in + r.cached * PRICE.cached + r.output * PRICE.out) / m;
};

async function runArm(halo: boolean) {
  const { Agent, Runner, OpenAIProvider, tool } = await import("@openai/agents");
  const getAttachment = tool({
    name: "get_attachment",
    description: "Fetch one clinical attachment body (narrative + findings + tooth chart + raw image) for review.",
    parameters: { type: "object", properties: { attachment_ref: { type: "string" } }, required: ["attachment_ref"], additionalProperties: false } as any,
    strict: false,
    execute: async () => JSON.stringify(DOC),
  });

  if (halo) {
    const { installHalo } = await import("@halo-format/openai");
    const installed = installHalo({ tools: [getAttachment], threshold: 2048 });
    const agent = new Agent({ name: "ab", instructions: HALO_GUIDANCE, tools: installed.tools as any[], model: MODEL });
    const runner = new Runner({ modelProvider: installed.wrapModelProvider(new OpenAIProvider()) });
    return meter(await runner.run(agent, TASK, { maxTurns: 30 }));
  }
  const agent = new Agent({ name: "ab", instructions: "", tools: [getAttachment], model: MODEL });
  return meter(await new Runner().run(agent, TASK, { maxTurns: 30 }));
}

async function main(): Promise<void> {
  console.log(`== Big-payload A/B (model ${MODEL}) ==`);
  console.log(`payload: ${JSON.stringify(DOC).length.toLocaleString()}B  (image_b64 ${(DOC.image_b64 as string).length.toLocaleString()}B)\n`);
  const base = await runArm(false);
  const halo = await runArm(true);
  for (const [label, r] of [["baseline", base], ["halo", halo]] as const) {
    console.log(`${label.padEnd(9)}| input=${r.input.toLocaleString().padStart(8)}  cached=${r.cached.toLocaleString().padStart(8)}  output=${r.output.toLocaleString().padStart(5)}  tools=${r.calls}  cost=$${cost(r).toFixed(4)}`);
  }
  const ingested = (r: { input: number; cached: number }) => Math.max(0, r.input - r.cached);
  const saved = ingested(base) ? 1 - ingested(halo) / ingested(base) : 0;
  const costSaved = cost(base) ? 1 - cost(halo) / cost(base) : 0;
  console.log(`\ncontext ingested (fresh input): ${ingested(base).toLocaleString()} -> ${ingested(halo).toLocaleString()}  (${(saved * 100).toFixed(0)}% less)`);
  console.log(`cost:                           $${cost(base).toFixed(4)} -> $${cost(halo).toFixed(4)}  (${(costSaved * 100).toFixed(0)}% less)`);
  console.log(`\nbaseline answer: ${base.answer.slice(0, 140)}`);
  console.log(`halo answer:     ${halo.answer.slice(0, 140)}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
