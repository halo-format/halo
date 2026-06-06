// ============================================================================
// Big-payload A/B: baseline (raw JSON) vs Halo, on one large attachment body.
//
// Self-contained — needs only ANTHROPIC_API_KEY (no database, no review gate). It builds
// a single get_attachment tool returning a realistic large dental attachment (small
// clinical fields + a ~200KB raw image_b64 blob), then asks the model a question it can
// answer from the small fields alone, twice:
//
//   baseline — the tool result lands in context whole; the blob is re-read every turn.
//   halo     — installHalo encodes the result; the model sees a shape map and halo_fetches
//              only kind/findings, so the blob never enters context.
//
// Add CACHE=1 to also turn on Anthropic prompt caching (applied to both arms).
//
//   npx tsx scripts/ab-big-payload.ts
//   IMAGE_KB=400 CACHE=1 npx tsx scripts/ab-big-payload.ts
// ============================================================================
import { createHash } from "node:crypto";
import { tool } from "@langchain/core/tools";
import { createAgent } from "langchain";
import { ChatAnthropic } from "@langchain/anthropic";
import { installHalo } from "@halo-format/langgraph";
import * as z from "zod";

const MODEL = process.env.AGENT_MODEL || "claude-sonnet-4-6";
const IMAGE_KB = Number(process.env.IMAGE_KB || "200");
const CACHE_ENABLED = ["1", "true", "yes", "on"].includes((process.env.CACHE || "").toLowerCase());

const HALO_GUIDANCE =
  "\n\nLarge tool results come back as a Halo shape map (a `[halo] map …` note with one line " +
  "per field: ref, kind, preview). Read the previews; for a field you still need call " +
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
    tooth_chart: chart, image_meta: { dpi: 300, bytes: IMAGE_KB * 1024, modality: "intraoral" },
    image_b64: imageB64,
  };
}

const DOC = attachmentBody();

const getAttachment = tool(async () => JSON.stringify(DOC), {
  name: "get_attachment",
  description: "Fetch one clinical attachment body (narrative + findings + tooth chart + raw image) for review.",
  schema: z.object({ attachment_ref: z.string() }),
});

type Stat = { input: number; output: number; cache_read: number; cache_write: number; tools: number; answer: string };

async function runArm(halo: boolean): Promise<Stat> {
  const model = new ChatAnthropic({ model: MODEL, maxTokens: 1000 });
  const middleware: any[] = [];
  if (CACHE_ENABLED) {
    const { promptCachingMiddleware } = await import("../src/caching.js");
    middleware.push(promptCachingMiddleware);
  }
  let agent: any;
  if (halo) {
    const installed = installHalo({ tools: [getAttachment], threshold: 2048 });
    agent = createAgent({ model, tools: installed.tools as any, middleware: [...middleware, ...installed.middleware] as any, systemPrompt: HALO_GUIDANCE });
  } else {
    agent = createAgent({ model, tools: [getAttachment], middleware: middleware as any });
  }

  const result: any = await agent.invoke({ messages: [{ role: "user", content: TASK }] }, { recursionLimit: 30 });
  const s: Stat = { input: 0, output: 0, cache_read: 0, cache_write: 0, tools: 0, answer: "" };
  for (const m of result.messages) {
    const um = m.usage_metadata;
    if (um) {
      const det = um.input_token_details || {};
      const cr = det.cache_read || 0;
      const cw = (det.cache_creation || 0) || ((det.ephemeral_5m_input_tokens || 0) + (det.ephemeral_1h_input_tokens || 0));
      s.input += Math.max(0, (um.input_tokens || 0) - cr - cw);
      s.output += um.output_tokens || 0;
      s.cache_read += cr;
      s.cache_write += cw;
    }
    for (const _ of m.tool_calls || []) s.tools += 1;
  }
  const last = result.messages[result.messages.length - 1];
  s.answer = (typeof last.content === "string" ? last.content : JSON.stringify(last.content)).trim();
  return s;
}

// sonnet-4-6 per-MTok: input 3, output 15, cache_read 0.3, cache_write 3.75
const cost = (s: Stat): number =>
  (s.input * 3 + s.output * 15 + s.cache_read * 0.3 + s.cache_write * 3.75) / 1_000_000;

async function main(): Promise<void> {
  console.log(`== Big-payload A/B (model ${MODEL}, cache=${CACHE_ENABLED ? "on" : "off"}) ==`);
  console.log(`payload: ${JSON.stringify(DOC).length.toLocaleString()}B  (image_b64 ${(DOC.image_b64 as string).length.toLocaleString()}B)\n`);
  const base = await runArm(false);
  const halo = await runArm(true);
  for (const [label, r] of [["baseline", base], ["halo", halo]] as [string, Stat][]) {
    console.log(`${label.padEnd(9)}| input=${String(r.input).padStart(8)}  output=${String(r.output).padStart(5)}  ` +
      `cache_read=${String(r.cache_read).padStart(8)}  cache_write=${String(r.cache_write).padStart(8)}  tools=${r.tools}  cost=$${cost(r).toFixed(4)}`);
  }
  const ingested = (r: Stat) => r.input + r.cache_write;
  const less = (a: number, b: number) => Math.round((1 - b / a) * 100);
  console.log(`\ncontext ingested (fresh+write): ${ingested(base).toLocaleString()} -> ${ingested(halo).toLocaleString()}  (${less(ingested(base), ingested(halo))}% less)`);
  console.log(`cost:                           $${cost(base).toFixed(4)} -> $${cost(halo).toFixed(4)}  (${less(cost(base), cost(halo))}% less)`);
  console.log(`\nbaseline answer: ${base.answer.slice(0, 140)}`);
  console.log(`halo answer:     ${halo.answer.slice(0, 140)}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
