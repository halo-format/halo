// ============================================================================
// The 15 payer tools as OpenAI Agents SDK function tools (TypeScript).
//
// Each tool wraps the same SQL on ext.*/agent.* and the same deterministic engine
// as every other port — only the framing changes (the OpenAI Agents SDK's `tool()`).
// Parameters are declared as plain JSON schemas with `strict: false`, so this example
// pulls in no zod and sidesteps the SDK's zod-version peer entirely. The raw async
// bodies are exported too, so the self-test (src/agent.ts --selftest) can call them
// directly without the model.
//
// The claim API is normalized REST-style (matching the other ports): `payer_get_claim`
// returns the header, lines, diagnosis, and an attachment MANIFEST — references and
// light metadata (kind, byte size, which line each documents), NOT the bodies. The
// bulky clinical bodies (narrative, findings, tooth chart, and a large raw `image_b64`
// blob) are fetched on demand with `payer_get_attachment` / `payer_get_attachments`
// only for a line that needs documentation review.
//
// NOTE: this example ships WITHOUT a Halo integration by default — tools return plain
// JSON. The Halo OpenAI-Agents host adapter attaches separately in src/agent.ts (HALO=1);
// the on-demand attachment body — narrative/findings the reviewer reads, plus an
// `image_b64` blob it never reads — is exactly the payload that adapter encodes.
// ============================================================================
import { createHash, randomUUID } from "node:crypto";
import { tool } from "@openai/agents";
import { q, one, pool } from "./db.js";
import { adjudicateLine, type EngineInputs } from "./engine.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

type Json = Record<string, any>;
const __dirname = dirname(fileURLToPath(import.meta.url));
const AUTO_FINALIZE_MAX_CENTS = Number(process.env.AUTO_FINALIZE_MAX_CENTS || "50000");

function promptHash(): string {
  try {
    return "sha256:" + createHash("sha256").update(readFileSync(join(__dirname, "..", "CLAUDE.md"))).digest("hex");
  } catch {
    return "sha256:unknown";
  }
}

const yearOf = (d: any): number =>
  d instanceof Date ? d.getUTCFullYear() : parseInt(String(d).slice(0, 4), 10);

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
// ── attachment synthesis (deterministic from claimId + ref) ──────────────────
// A claim references attachments; the bodies are retrieved separately. The body carries
// a large raw image blob (image_b64) a reviewer never reads — only narrative/findings
// matter — which is exactly the field Halo lets the model skip.
const ATTACH_KINDS = ["periapical_xray", "bitewing_xray", "panoramic_xray", "perio_chart", "clinical_note"];
const NARRATIVE =
  "Patient presents for evaluation. Intraoral examination performed; findings documented " +
  "per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment " +
  "plan discussed with the patient and informed consent obtained. No adverse reaction noted.";
const FINDINGS = [
  "Radiograph supports the proposed restoration; margins intact, no periapical pathology.",
  "Generalized moderate periodontitis; scaling and root planing indicated for the quadrant.",
  "Deep carious lesion approximating the pulp; crown indicated to restore the tooth.",
  "No acute findings; documentation supports the submitted procedure.",
];

// Major restorative / endodontic / periodontal / oral-surgery codes need a clinical
// attachment. Preventive (D01/D11) and basic single-surface restorations do not.
function needsDocumentation(code: string): boolean {
  const c = (code || "").toUpperCase();
  return (
    c.startsWith("D27") || c.startsWith("D6") || // crowns / fixed prosthodontics
    c.startsWith("D3") ||                         // endodontics
    (c.startsWith("D4") && c >= "D4210") ||       // periodontal surgery / scaling
    c.startsWith("D7")                            // oral surgery
  );
}

// Deterministic scalar fields for one attachment, in a FIXED order so the manifest
// (get_claim) and the body (get_attachment) always agree.
function attachmentFields(claimId: string, ref: string) {
  const rng = mulberry32(parseInt(createHash("sha256").update(`${claimId}/${ref}`).digest("hex").slice(0, 8), 16));
  const kind = ATTACH_KINDS[Math.floor(rng() * ATTACH_KINDS.length)];
  const capturedAt = `2026-0${1 + Math.floor(rng() * 5)}-${10 + Math.floor(rng() * 18)}`;
  const imageKb = 18 + Math.floor(rng() * 22); // the bulky raw-image payload, in KB
  const narrativeRepeat = 2 + Math.floor(rng() * 3);
  const finding = FINDINGS[Math.floor(rng() * FINDINGS.length)];
  return { kind, capturedAt, imageKb, narrativeRepeat, finding };
}

// Light per-attachment metadata: ref, kind, capture date, byte size, and which line it
// documents. No bodies — this is what a claim fetch should return.
function attachmentManifest(claimId: string, lines: Json[], refs: string[]): Json[] {
  const docLines = (lines || []).filter((l) => needsDocumentation(l.procedure_code)).map((l) => l.line_number);
  return (refs || []).map((ref, i) => {
    const { kind, capturedAt, imageKb } = attachmentFields(claimId, ref);
    return {
      ref, kind, captured_at: capturedAt, modality: "intraoral",
      image_bytes: imageKb * 1024,
      documents_line: i < docLines.length ? docLines[i] : null,
    };
  });
}

// The full attachment: narrative + findings + tooth chart + a large raw image blob.
// image_b64 is the bulk — a reviewer reads narrative/findings, never the pixels.
function attachmentBody(claimId: string, ref: string): Json {
  const { kind, capturedAt, imageKb, narrativeRepeat, finding } = attachmentFields(claimId, ref);
  const chartRng = mulberry32(parseInt(createHash("sha256").update(`${claimId}/${ref}/chart`).digest("hex").slice(0, 8), 16));
  const chart: Record<string, string> = {};
  for (let t = 1; t <= 32; t++) chart[t] = ["sound", "restored", "caries", "missing"][Math.floor(chartRng() * 4)];
  const unit = createHash("sha256").update(`${claimId}/${ref}/image`).digest("base64");
  const imageB64 = unit.repeat(Math.ceil((imageKb * 1024) / unit.length)).slice(0, imageKb * 1024);
  return {
    attachment_ref: ref, claim_id: claimId, kind, captured_at: capturedAt,
    narrative: Array(narrativeRepeat).fill(NARRATIVE).join(" "),
    findings: finding,
    tooth_chart: chart,
    image_meta: { dpi: 300, bytes: imageKb * 1024, modality: "intraoral" },
    image_b64: imageB64, // raw pixels — large, not human-readable; do not fetch for review
  };
}

// ── raw tool bodies (exported for the self-test) ─────────────────────────────
export async function payer_get_agent_provenance(): Promise<string> {
  return JSON.stringify({ prompt_version_hash: promptHash(), prompt_source: "CLAUDE.md", agent_id: "insurance-claim-decision-agent" });
}

export async function payer_get_claim({ claim_id }: { claim_id: string }): Promise<string> {
  const claim = await one("SELECT * FROM ext.claims WHERE id=$1", [claim_id]);
  if (!claim) return JSON.stringify({ error: "claim_not_found", claim_id });
  const lines = await q("SELECT * FROM ext.claim_lines WHERE claim_id=$1 ORDER BY line_number", [claim_id]);
  return JSON.stringify({ ...claim, lines, attachments: attachmentManifest(claim.id, lines, claim.attachments || []) });
}

export async function payer_get_attachment({ claim_id, attachment_ref }: { claim_id: string; attachment_ref: string }): Promise<string> {
  const claim = await one("SELECT attachments FROM ext.claims WHERE id=$1", [claim_id]);
  if (!claim) return JSON.stringify({ error: "claim_not_found", claim_id });
  if (!(claim.attachments || []).includes(attachment_ref))
    return JSON.stringify({ error: "attachment_not_found", claim_id, attachment_ref });
  return JSON.stringify(attachmentBody(claim_id, attachment_ref));
}

export async function payer_get_attachments({ claim_id, attachment_refs }: { claim_id: string; attachment_refs: string[] }): Promise<string> {
  const claim = await one("SELECT attachments FROM ext.claims WHERE id=$1", [claim_id]);
  if (!claim) return JSON.stringify({ error: "claim_not_found", claim_id });
  const valid = new Set<string>(claim.attachments || []);
  return JSON.stringify({ claim_id, attachments: (attachment_refs || []).filter((r) => valid.has(r)).map((r) => attachmentBody(claim_id, r)) });
}

export async function payer_get_member_coverage({ member_id }: { member_id: string }): Promise<string> {
  const member = await one("SELECT * FROM ext.members WHERE id=$1", [member_id]);
  if (!member) return JSON.stringify({ error: "member_not_found", member_id });
  const plan = await one("SELECT * FROM ext.plans WHERE id=$1", [member.plan_id]);
  return JSON.stringify({ member, plan });
}

export async function payer_get_benefit_rules({ plan_id, procedure_codes }: { plan_id: string; procedure_codes?: string[] }): Promise<string> {
  const rules = procedure_codes && procedure_codes.length
    ? await q("SELECT * FROM ext.benefit_rules WHERE plan_id=$1 AND procedure_code=ANY($2::text[])", [plan_id, procedure_codes])
    : await q("SELECT * FROM ext.benefit_rules WHERE plan_id=$1", [plan_id]);
  return JSON.stringify({ plan_id, rules });
}

export async function payer_get_accumulators({ member_id, plan_year }: { member_id: string; plan_year: number }): Promise<string> {
  const r = await one("SELECT * FROM ext.accumulators WHERE member_id=$1 AND plan_year=$2", [member_id, plan_year]);
  return JSON.stringify(r ?? { member_id, plan_year, deductible_met_cents: 0, annual_max_used_cents: 0, oop_met_cents: 0 });
}

export async function payer_get_claim_history({ member_id, procedure_code, window_days }: { member_id: string; procedure_code?: string; window_days?: number }): Promise<string> {
  const since = new Date(Date.now() - (window_days ?? 365) * 86400_000).toISOString().slice(0, 10);
  const lines = procedure_code
    ? await q(`SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id=cl.claim_id
         WHERE c.member_id=$1 AND cl.procedure_code=$2 AND cl.date_of_service>=$3 ORDER BY cl.date_of_service DESC`, [member_id, procedure_code, since])
    : await q(`SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id=cl.claim_id
         WHERE c.member_id=$1 AND cl.date_of_service>=$2 AND c.status<>'received' ORDER BY cl.date_of_service DESC`, [member_id, since]);
  return JSON.stringify({ member_id, procedure_code: procedure_code ?? null, lines });
}

export async function payer_check_network({ provider_id, plan_id }: { provider_id: string; plan_id: string }): Promise<string> {
  const r = await one("SELECT * FROM ext.network WHERE plan_id=$1 AND provider_id=$2", [plan_id, provider_id]);
  return JSON.stringify(r ? { ...r, on_file: true } : { plan_id, provider_id, in_network: false, on_file: false });
}

export async function payer_get_allowed_amount({ plan_id, procedure_codes }: { plan_id: string; procedure_codes: string[] }): Promise<string> {
  const rows = await q("SELECT procedure_code, allowed_cents FROM ext.fee_schedule WHERE plan_id=$1 AND procedure_code=ANY($2::text[])", [plan_id, procedure_codes]);
  const allowed: Record<string, number> = {};
  for (const r of rows) allowed[r.procedure_code] = r.allowed_cents;
  return JSON.stringify({ plan_id, allowed });
}

export async function payer_lookup_reason_code({ code }: { code: string }): Promise<string> {
  const r = await one("SELECT * FROM ext.reason_codes WHERE code=$1", [code]);
  return JSON.stringify(r ?? { error: "unknown_reason_code", code });
}

export async function payer_adjudicate_line({ claim_id, line_number }: { claim_id: string; line_number: number }): Promise<string> {
  const line = await one("SELECT * FROM ext.claim_lines WHERE claim_id=$1 AND line_number=$2", [claim_id, line_number]);
  if (!line) return JSON.stringify({ error: "line_not_found", claim_id, line_number });
  const claim = await one("SELECT * FROM ext.claims WHERE id=$1", [claim_id]);
  const member = await one("SELECT * FROM ext.members WHERE id=$1", [claim.member_id]);
  const plan = await one("SELECT * FROM ext.plans WHERE id=$1", [member.plan_id]);
  const rule = await one("SELECT * FROM ext.benefit_rules WHERE plan_id=$1 AND procedure_code=$2", [plan.id, line.procedure_code]);
  const allowedRow = await one("SELECT allowed_cents FROM ext.fee_schedule WHERE plan_id=$1 AND procedure_code=$2", [plan.id, line.procedure_code]);
  const net = await one("SELECT * FROM ext.network WHERE plan_id=$1 AND provider_id=$2", [plan.id, claim.provider_id]);
  const acc = await one("SELECT * FROM ext.accumulators WHERE member_id=$1 AND plan_year=$2", [member.id, yearOf(line.date_of_service)]);
  if (allowedRow == null) return JSON.stringify({ error: "no_fee_schedule", claim_id, line_number });

  const ruleD = rule ?? { covered: false, coverage_pct: 0 };
  const accD = acc ?? { deductible_met_cents: 0, annual_max_used_cents: 0, oop_met_cents: 0 };
  const inputs: EngineInputs = {
    line: { procedure_code: line.procedure_code, units: line.units, charged_cents: line.charged_cents },
    rule: { covered: ruleD.covered, coverage_pct: ruleD.coverage_pct },
    accumulators: { deductible_met_cents: accD.deductible_met_cents, annual_max_used_cents: accD.annual_max_used_cents },
    allowed_cents: allowedRow.allowed_cents, network: { in_network: net ? !!net.in_network : false },
    plan: { deductible_cents: plan.deductible_cents, annual_max_cents: plan.annual_max_cents },
  };
  return JSON.stringify({ ...adjudicateLine(inputs), claim_id, line_number, procedure_code: line.procedure_code });
}

export async function payer_record_decision({ claim_id, lines }: { claim_id: string; model_version: string; prompt_version_hash: string; lines: Json[] }): Promise<string> {
  const claim = await one("SELECT * FROM ext.claims WHERE id=$1", [claim_id]);
  if (!claim) return JSON.stringify({ error: "claim_not_found", claim_id });
  const adverse = lines.some((l: Json) => ["deny", "reduce", "pend"].includes(l.decision));
  const above = (claim.total_charged_cents || 0) > AUTO_FINALIZE_MAX_CENTS;
  const client = await pool().connect();
  try {
    await client.query("BEGIN");
    for (const l of lines as Json[]) {
      await client.query(
        `INSERT INTO agent.decisions (claim_id, line_number, decision, allowed_cents, plan_paid_cents,
           patient_resp_cents, deductible_cents, coinsurance_cents, copay_cents, carc, rarc, rule_basis,
           computed_by, status, rationale)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,'engine','proposed',$13)
         ON CONFLICT (claim_id, line_number) DO UPDATE SET decision=EXCLUDED.decision, allowed_cents=EXCLUDED.allowed_cents,
           plan_paid_cents=EXCLUDED.plan_paid_cents, patient_resp_cents=EXCLUDED.patient_resp_cents,
           deductible_cents=EXCLUDED.deductible_cents, coinsurance_cents=EXCLUDED.coinsurance_cents,
           copay_cents=EXCLUDED.copay_cents, carc=EXCLUDED.carc, rarc=EXCLUDED.rarc, rule_basis=EXCLUDED.rule_basis,
           rationale=EXCLUDED.rationale, status='proposed'`,
        [claim_id, l.line_number, l.decision, l.allowed_cents ?? 0, l.plan_paid_cents ?? 0, l.patient_resp_cents ?? 0,
         l.deductible_cents ?? 0, l.coinsurance_cents ?? 0, l.copay_cents ?? 0,
         JSON.stringify(l.carc ?? []), JSON.stringify(l.rarc ?? []), JSON.stringify(l.rule_basis ?? []), l.rationale ?? ""]);
    }
    await client.query("UPDATE ext.claims SET status=$1 WHERE id=$2", [lines.some((l: Json) => l.decision === "pend") ? "pended" : "received", claim_id]);
    await client.query("COMMIT");
  } catch (e) { await client.query("ROLLBACK"); throw e; } finally { client.release(); }
  return JSON.stringify({ claim_id, lines_recorded: lines.length, requires_human: adverse || above, reason: adverse ? "adverse_line" : above ? "above_ceiling" : "none" });
}

async function reviewResult(id: string): Promise<string> {
  const r = await one("SELECT * FROM agent.approvals WHERE id=$1", [id]);
  return JSON.stringify({ approval_id: r.id, claim_id: r.claim_id, status: r.status, is_override: r.is_override, decided_by: r.decided_by, line_overrides: r.line_overrides, justification: r.justification });
}

export async function payer_request_review({ claim_id, summary, reason }: { claim_id: string; summary: string; reason?: string }): Promise<string> {
  const timeout = Number(process.env.APPROVAL_TIMEOUT_SECONDS || "900");
  const poll = Number(process.env.APPROVAL_POLL_SECONDS || "2");
  const proposed = await q("SELECT line_number, decision, plan_paid_cents, patient_resp_cents FROM agent.decisions WHERE claim_id=$1 ORDER BY line_number", [claim_id]);
  const existing = await one("SELECT id, status FROM agent.approvals WHERE idempotency_key=$1", [claim_id]);
  let approvalId: string;
  if (existing && existing.status !== "pending") return reviewResult(existing.id);
  if (existing) approvalId = existing.id;
  else {
    approvalId = randomUUID();
    await q("INSERT INTO agent.approvals (id, claim_id, action, payload, idempotency_key) VALUES ($1,$2,'claim_review',$3::jsonb,$4)",
      [approvalId, claim_id, JSON.stringify({ summary, reason: reason ?? "adverse_or_above_threshold", proposed }), claim_id]);
  }
  let waited = 0;
  while (waited < timeout) {
    const s = (await one("SELECT status FROM agent.approvals WHERE id=$1", [approvalId]))?.status;
    if (s && s !== "pending") return reviewResult(approvalId);
    await new Promise((r) => setTimeout(r, poll * 1000)); waited += poll;
  }
  return JSON.stringify({ status: "timeout", approval_id: approvalId });
}

const STATUS_MAP: Record<string, string> = { pay: "paid", reduce: "reduced", deny: "denied", pend: "pended" };
export async function payer_post_adjudication({ claim_id }: { claim_id: string }): Promise<string> {
  const decisions = await q("SELECT * FROM agent.decisions WHERE claim_id=$1 ORDER BY line_number", [claim_id]);
  if (decisions.length === 0) return JSON.stringify({ error: "no_decisions", claim_id });
  const appr = await one("SELECT * FROM agent.approvals WHERE idempotency_key=$1", [claim_id]);
  if (appr && appr.status === "pending") return JSON.stringify({ error: "review_pending", claim_id });
  const overrides = (appr && appr.line_overrides) || {};
  const client = await pool().connect();
  const posted: Json[] = [];
  try {
    await client.query("BEGIN");
    for (const d of decisions) {
      const ov = overrides[String(d.line_number)] || {};
      const decision = ov.decision ?? d.decision;
      const planPaid = ov.plan_paid_cents ?? d.plan_paid_cents;
      const patient = ov.patient_resp_cents ?? d.patient_resp_cents;
      const status = STATUS_MAP[decision] ?? "pended";
      await client.query(`UPDATE ext.claim_lines SET status=$1, allowed_cents=$2, plan_paid_cents=$3, patient_resp_cents=$4, carc=$5::jsonb, rarc=$6::jsonb WHERE claim_id=$7 AND line_number=$8`,
        [status, d.allowed_cents, planPaid, patient, JSON.stringify(d.carc ?? []), JSON.stringify(d.rarc ?? []), claim_id, d.line_number]);
      await client.query("UPDATE agent.decisions SET status='final', decided_at=now(), approver=$1 WHERE claim_id=$2 AND line_number=$3", [appr?.decided_by ?? null, claim_id, d.line_number]);
      posted.push({ line_number: d.line_number, status, plan_paid_cents: planPaid, patient_resp_cents: patient });
    }
    const statuses = new Set(posted.map((p) => p.status));
    const claimStatus = statuses.has("pended") ? "pended" : statuses.size === 1 && statuses.has("denied") ? "denied" : "adjudicated";
    await client.query("UPDATE ext.claims SET status=$1 WHERE id=$2", [claimStatus, claim_id]);
    await client.query("COMMIT");
    return JSON.stringify({ claim_id, claim_status: claimStatus, lines: posted,
      total_plan_paid_cents: posted.reduce((s, p) => s + (p.plan_paid_cents || 0), 0),
      total_patient_resp_cents: posted.reduce((s, p) => s + (p.patient_resp_cents || 0), 0) });
  } catch (e) { await client.query("ROLLBACK"); throw e; } finally { client.release(); }
}

// ── registration ───────────────────────────────────────────────────────────────
// Each tool: JSON-schema parameters + `strict: false` (so no zod, and free-form line
// objects are allowed). execute receives the parsed args; we cast to the body's param shape.
const STR = { type: "string" } as const;
function P(properties: Record<string, unknown>, required: string[]): any {
  return { type: "object", properties, required, additionalProperties: false };
}
function mk<A>(name: string, description: string, parameters: any, body: (a: A) => Promise<string>) {
  return tool({ name, description, parameters, strict: false, execute: (input: unknown) => body(input as A) });
}

export const TOOLS = [
  mk("payer_get_agent_provenance", "Return the canonical prompt_version_hash (sha256 over CLAUDE.md). Call before recording.",
    P({}, []), () => payer_get_agent_provenance()),
  mk("payer_get_claim", "Fetch the 837 claim: header, service lines, diagnosis, and an attachment MANIFEST (refs + metadata, not bodies). Fetch bodies on demand with payer_get_attachment when a line needs documentation review.",
    P({ claim_id: STR }, ["claim_id"]), payer_get_claim),
  mk("payer_get_attachment", "Fetch ONE attachment's full body (narrative + findings + tooth chart + raw image_b64) for documentation review. Large — read narrative/findings, never image_b64. Only for a line needing documentation (major restorative, endodontic, periodontal, oral surgery).",
    P({ claim_id: STR, attachment_ref: STR }, ["claim_id", "attachment_ref"]), payer_get_attachment),
  mk("payer_get_attachments", "Batch form of payer_get_attachment — fetch several attachment bodies in one call.",
    P({ claim_id: STR, attachment_refs: { type: "array", items: STR } }, ["claim_id", "attachment_refs"]), payer_get_attachments),
  mk("payer_get_member_coverage", "Member eligibility, effective dates, and the plan benefit design.",
    P({ member_id: STR }, ["member_id"]), payer_get_member_coverage),
  mk("payer_get_benefit_rules", "Per-code coverage %, frequency, waiting, preauth, category. Pass this claim's codes only.",
    P({ plan_id: STR, procedure_codes: { type: "array", items: STR } }, ["plan_id"]), payer_get_benefit_rules),
  mk("payer_get_accumulators", "Deductible met, annual max used, OOP met for the plan year.",
    P({ member_id: STR, plan_year: { type: "integer" } }, ["member_id", "plan_year"]), payer_get_accumulators),
  mk("payer_get_claim_history", "Prior adjudicated lines for frequency/duplicate checks (heavy). Slice with procedure_code.",
    P({ member_id: STR, procedure_code: STR, window_days: { type: "integer" } }, ["member_id"]), payer_get_claim_history),
  mk("payer_check_network", "In / out of network for (provider, plan).",
    P({ provider_id: STR, plan_id: STR }, ["provider_id", "plan_id"]), payer_check_network),
  mk("payer_get_allowed_amount", "Fee-schedule allowed amounts for the codes on the claim.",
    P({ plan_id: STR, procedure_codes: { type: "array", items: STR } }, ["plan_id", "procedure_codes"]), payer_get_allowed_amount),
  mk("payer_lookup_reason_code", "CARC / RARC description. Select from these; never invent a code.",
    P({ code: STR }, ["code"]), payer_lookup_reason_code),
  mk("payer_adjudicate_line", "Run the DETERMINISTIC engine on one line. Fetches its own inputs; returns the money + suggested CARC/RARC + review flags. The model never supplies or computes an amount.",
    P({ claim_id: STR, line_number: { type: "integer" } }, ["claim_id", "line_number"]), payer_adjudicate_line),
  mk("payer_record_decision", "Persist proposed per-line decisions (status 'proposed'). lines is a list of per-line decision objects. Computes requires_human: any deny/reduce/pend, or a claim above the ceiling.",
    P({ claim_id: STR, model_version: STR, prompt_version_hash: STR, lines: { type: "array", items: { type: "object", additionalProperties: true } } }, ["claim_id", "model_version", "prompt_version_hash", "lines"]), payer_record_decision),
  mk("payer_request_review", "Open the human review gate; BLOCKS until a claims examiner resolves it.",
    P({ claim_id: STR, summary: STR, reason: STR }, ["claim_id", "summary"]), payer_request_review),
  mk("payer_post_adjudication", "Commit final decisions to ext.claim_lines (the 835/EOB). Idempotent per (claim_id, line_number).",
    P({ claim_id: STR }, ["claim_id"]), payer_post_adjudication),
];
