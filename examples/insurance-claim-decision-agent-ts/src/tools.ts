// ============================================================================
// The payer tool layer — the 13 domain tools, as plain functions + raw Messages
// API tool definitions. A port of server.py: SQL on ext.* (the payer mirror) and
// read/write on agent.* (the agent's own state). The contract is the swap point.
//
// Three load-bearing properties, enforced here:
//  * payer_adjudicate_line runs the DETERMINISTIC engine on inputs it fetches
//    itself — the model never supplies or computes an amount.
//  * Every input the engine touched is written to the content-addressed store
//    (agent.halo_nodes) and its handle recorded as the decision's evidence —
//    tamper-evident, byte-identical to the Python port (shared @halo-format/halo).
//  * payer_request_review BLOCKS until a human resolves the gate;
//    payer_post_adjudication is idempotent per (claim_id, line_number).
// ============================================================================
import { createHash } from "node:crypto";
import { canonicalBytes, handleOf } from "@halo-format/halo";
import { q, one, pool } from "./db.js";
import { adjudicateLine, type EngineInputs } from "./engine.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

type Json = Record<string, any>;
const __dirname = dirname(fileURLToPath(import.meta.url));
const AUTO_FINALIZE_MAX_CENTS = Number(process.env.AUTO_FINALIZE_MAX_CENTS || "50000");

function promptVersionHash(): string {
  try {
    const bytes = readFileSync(join(__dirname, "..", "CLAUDE.md"));
    return "sha256:" + createHash("sha256").update(bytes).digest("hex");
  } catch {
    return "sha256:" + createHash("sha256").update("fallback").digest("hex");
  }
}

// Write a value into the content-addressed store; return its (Halo) handle.
async function putNode(value: unknown): Promise<string> {
  const handle = handleOf(value as any);
  await q(
    "INSERT INTO agent.halo_nodes (handle, bytes) VALUES ($1, $2) ON CONFLICT (handle) DO NOTHING",
    [handle, Buffer.from(canonicalBytes(value as any))],
  );
  return handle;
}

const yearOf = (d: any): number =>
  d instanceof Date ? d.getUTCFullYear() : parseInt(String(d).slice(0, 4), 10);

// ── deterministic, bulky clinical attachment bodies (the Halo payload) ───────
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function attachmentBodies(claimId: string, refs: string[]): Json[] {
  const seed = parseInt(createHash("sha256").update(claimId).digest("hex").slice(0, 8), 16);
  const rng = mulberry32(seed);
  const pick = <T>(a: T[]): T => a[Math.floor(rng() * a.length)];
  const para =
    "Patient presents for evaluation. Intraoral examination performed; findings documented per " +
    "chart. Radiographic series reviewed. Treatment plan discussed and consent obtained. No adverse " +
    "reaction noted during procedure.";
  return (refs || []).map((ref) => {
    const chart: Record<string, string> = {};
    for (let t = 1; t <= 32; t++) chart[t] = pick(["sound", "restored", "caries", "missing"]);
    return {
      attachment_ref: ref,
      kind: pick(["clinical_note", "periapical_xray", "bitewing_xray", "perio_chart"]),
      captured_at: `2026-0${1 + Math.floor(rng() * 5)}-${10 + Math.floor(rng() * 18)}`,
      narrative: Array(2 + Math.floor(rng() * 3)).fill(para).join(" "),
      tooth_chart: chart,
      image_meta: { dpi: 300, bytes: 180000 + Math.floor(rng() * 740000), modality: "intraoral" },
    };
  });
}

// ── 0. provenance ─────────────────────────────────────────────────────────────
async function payer_get_agent_provenance(): Promise<Json> {
  return { prompt_version_hash: promptVersionHash(), prompt_source: "CLAUDE.md", agent_id: "insurance-claim-decision-agent" };
}

// ── 1. get_claim (heavy) ──────────────────────────────────────────────────────
async function payer_get_claim(a: Json): Promise<Json> {
  const claim = await one("SELECT * FROM ext.claims WHERE id = $1", [a.claim_id]);
  if (!claim) return { error: "claim_not_found", claim_id: a.claim_id };
  const lines = await q("SELECT * FROM ext.claim_lines WHERE claim_id = $1 ORDER BY line_number", [a.claim_id]);
  return { ...claim, lines, attachment_bodies: attachmentBodies(claim.id, claim.attachments || []) };
}

// ── 2. get_member_coverage ────────────────────────────────────────────────────
async function payer_get_member_coverage(a: Json): Promise<Json> {
  const member = await one("SELECT * FROM ext.members WHERE id = $1", [a.member_id]);
  if (!member) return { error: "member_not_found", member_id: a.member_id };
  const plan = await one("SELECT * FROM ext.plans WHERE id = $1", [member.plan_id]);
  return { member, plan };
}

// ── 3. get_benefit_rules ──────────────────────────────────────────────────────
async function payer_get_benefit_rules(a: Json): Promise<Json> {
  const codes = a.procedure_codes as string[] | undefined;
  const rules = codes && codes.length
    ? await q("SELECT * FROM ext.benefit_rules WHERE plan_id = $1 AND procedure_code = ANY($2::text[])", [a.plan_id, codes])
    : await q("SELECT * FROM ext.benefit_rules WHERE plan_id = $1", [a.plan_id]);
  return { plan_id: a.plan_id, rules };
}

// ── 4. get_accumulators ───────────────────────────────────────────────────────
async function payer_get_accumulators(a: Json): Promise<Json> {
  const rec = await one("SELECT * FROM ext.accumulators WHERE member_id = $1 AND plan_year = $2", [a.member_id, a.plan_year]);
  return rec ?? { member_id: a.member_id, plan_year: a.plan_year, deductible_met_cents: 0, annual_max_used_cents: 0, oop_met_cents: 0 };
}

// ── 5. get_claim_history (heavy) ──────────────────────────────────────────────
async function payer_get_claim_history(a: Json): Promise<Json> {
  const windowDays = Number(a.window_days ?? 365);
  const since = new Date(Date.now() - windowDays * 86400_000).toISOString().slice(0, 10);
  const lines = a.procedure_code
    ? await q(
        `SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id = cl.claim_id
         WHERE c.member_id = $1 AND cl.procedure_code = $2 AND cl.date_of_service >= $3
         ORDER BY cl.date_of_service DESC`,
        [a.member_id, a.procedure_code, since],
      )
    : await q(
        `SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id = cl.claim_id
         WHERE c.member_id = $1 AND cl.date_of_service >= $2 AND c.status <> 'received'
         ORDER BY cl.date_of_service DESC`,
        [a.member_id, since],
      );
  return { member_id: a.member_id, procedure_code: a.procedure_code ?? null, lines };
}

// ── 6. check_network ──────────────────────────────────────────────────────────
async function payer_check_network(a: Json): Promise<Json> {
  const rec = await one("SELECT * FROM ext.network WHERE plan_id = $1 AND provider_id = $2", [a.plan_id, a.provider_id]);
  if (!rec) return { plan_id: a.plan_id, provider_id: a.provider_id, in_network: false, on_file: false };
  return { ...rec, on_file: true };
}

// ── 7. get_allowed_amount ─────────────────────────────────────────────────────
async function payer_get_allowed_amount(a: Json): Promise<Json> {
  const rows = await q("SELECT procedure_code, allowed_cents FROM ext.fee_schedule WHERE plan_id = $1 AND procedure_code = ANY($2::text[])", [a.plan_id, a.procedure_codes]);
  const allowed: Record<string, number> = {};
  for (const r of rows) allowed[r.procedure_code] = r.allowed_cents;
  return { plan_id: a.plan_id, allowed };
}

// ── 8. lookup_reason_code ─────────────────────────────────────────────────────
async function payer_lookup_reason_code(a: Json): Promise<Json> {
  const rec = await one("SELECT * FROM ext.reason_codes WHERE code = $1", [a.code]);
  return rec ?? { error: "unknown_reason_code", code: a.code };
}

// ── 9. adjudicate_line (DETERMINISTIC engine) ─────────────────────────────────
async function payer_adjudicate_line(a: Json): Promise<Json> {
  const line = await one("SELECT * FROM ext.claim_lines WHERE claim_id = $1 AND line_number = $2", [a.claim_id, a.line_number]);
  if (!line) return { error: "line_not_found", claim_id: a.claim_id, line_number: a.line_number };
  const claim = await one("SELECT * FROM ext.claims WHERE id = $1", [a.claim_id]);
  const member = await one("SELECT * FROM ext.members WHERE id = $1", [claim.member_id]);
  const plan = await one("SELECT * FROM ext.plans WHERE id = $1", [member.plan_id]);
  const rule = await one("SELECT * FROM ext.benefit_rules WHERE plan_id = $1 AND procedure_code = $2", [plan.id, line.procedure_code]);
  const allowedRow = await one("SELECT allowed_cents FROM ext.fee_schedule WHERE plan_id = $1 AND procedure_code = $2", [plan.id, line.procedure_code]);
  const net = await one("SELECT * FROM ext.network WHERE plan_id = $1 AND provider_id = $2", [plan.id, claim.provider_id]);
  const planYear = yearOf(line.date_of_service);
  const acc = await one("SELECT * FROM ext.accumulators WHERE member_id = $1 AND plan_year = $2", [member.id, planYear]);

  if (allowedRow == null) return { error: "no_fee_schedule", claim_id: a.claim_id, line_number: a.line_number, procedure_code: line.procedure_code };

  const ruleD = rule ?? { covered: false, coverage_pct: 0 };
  const accD = acc ?? { deductible_met_cents: 0, annual_max_used_cents: 0, oop_met_cents: 0 };
  const netD = { in_network: net ? !!net.in_network : false, on_file: !!net };

  const inputs: EngineInputs = {
    line: { procedure_code: line.procedure_code, units: line.units, charged_cents: line.charged_cents },
    rule: { covered: ruleD.covered, coverage_pct: ruleD.coverage_pct },
    accumulators: { deductible_met_cents: accD.deductible_met_cents, annual_max_used_cents: accD.annual_max_used_cents },
    allowed_cents: allowedRow.allowed_cents,
    network: { in_network: netD.in_network },
    plan: { deductible_cents: plan.deductible_cents, annual_max_cents: plan.annual_max_cents },
  };
  const result = adjudicateLine(inputs);

  // Pin every input the engine used; the handles are the decision's evidence.
  const evidence = {
    line: await putNode(line),
    benefit_rule: await putNode(ruleD),
    accumulators: await putNode(accD),
    fee_schedule: await putNode({ procedure_code: line.procedure_code, allowed_cents: allowedRow.allowed_cents }),
    network: await putNode(netD),
    plan_benefit: await putNode({ id: plan.id, type: plan.type, deductible_cents: plan.deductible_cents, annual_max_cents: plan.annual_max_cents, coinsurance: plan.coinsurance }),
  };
  return { ...result, claim_id: a.claim_id, line_number: a.line_number, procedure_code: line.procedure_code, evidence };
}

// ── 10. record_decision ───────────────────────────────────────────────────────
async function payer_record_decision(a: Json): Promise<Json> {
  const claim = await one("SELECT * FROM ext.claims WHERE id = $1", [a.claim_id]);
  if (!claim) return { error: "claim_not_found", claim_id: a.claim_id };
  const lines = (a.lines as Json[]) || [];
  const adverse = lines.some((l) => ["deny", "reduce", "pend"].includes(l.decision));
  const aboveCeiling = (claim.total_charged_cents || 0) > AUTO_FINALIZE_MAX_CENTS;
  const requiresHuman = adverse || aboveCeiling;

  const client = await pool().connect();
  try {
    await client.query("BEGIN");
    for (const l of lines) {
      const refs = Array.isArray(l.evidence) ? l.evidence : Object.values(l.evidence || {});
      const decisionRecord = await putNode({ model_version: a.model_version, prompt_version_hash: a.prompt_version_hash, decision: l.decision, carc: l.carc ?? [], refs });
      const evidence = JSON.stringify({ refs, decision_record: decisionRecord });
      await client.query(
        `INSERT INTO agent.decisions
           (claim_id, line_number, decision, allowed_cents, plan_paid_cents, patient_resp_cents,
            deductible_cents, coinsurance_cents, copay_cents, carc, rarc, rule_basis, evidence,
            computed_by, status, rationale)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,'engine','proposed',$14)
         ON CONFLICT (claim_id, line_number) DO UPDATE SET
           decision=EXCLUDED.decision, allowed_cents=EXCLUDED.allowed_cents, plan_paid_cents=EXCLUDED.plan_paid_cents,
           patient_resp_cents=EXCLUDED.patient_resp_cents, deductible_cents=EXCLUDED.deductible_cents,
           coinsurance_cents=EXCLUDED.coinsurance_cents, copay_cents=EXCLUDED.copay_cents, carc=EXCLUDED.carc,
           rarc=EXCLUDED.rarc, rule_basis=EXCLUDED.rule_basis, evidence=EXCLUDED.evidence,
           rationale=EXCLUDED.rationale, status='proposed'`,
        [a.claim_id, l.line_number, l.decision, l.allowed_cents ?? 0, l.plan_paid_cents ?? 0, l.patient_resp_cents ?? 0,
         l.deductible_cents ?? 0, l.coinsurance_cents ?? 0, l.copay_cents ?? 0,
         JSON.stringify(l.carc ?? []), JSON.stringify(l.rarc ?? []), JSON.stringify(l.rule_basis ?? []), evidence, l.rationale ?? ""],
      );
    }
    const newStatus = lines.some((l) => l.decision === "pend") ? "pended" : "received";
    await client.query("UPDATE ext.claims SET status = $1 WHERE id = $2", [newStatus, a.claim_id]);
    await client.query("COMMIT");
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
  return {
    claim_id: a.claim_id, lines_recorded: lines.length,
    decisions: lines.map((l) => ({ line_number: l.line_number, decision: l.decision })),
    requires_human: requiresHuman, reason: adverse ? "adverse_line" : aboveCeiling ? "above_ceiling" : "none",
  };
}

// ── 11. request_review (HITL — blocks) ────────────────────────────────────────
async function reviewResult(id: string): Promise<Json> {
  const r = await one("SELECT * FROM agent.approvals WHERE id = $1", [id]);
  return {
    approval_id: r.id, claim_id: r.claim_id, status: r.status, is_override: r.is_override,
    decided_by: r.decided_by, line_overrides: r.line_overrides, justification: r.justification,
    decided_at: r.decided_at,
  };
}
async function payer_request_review(a: Json): Promise<Json> {
  const timeout = Number(process.env.APPROVAL_TIMEOUT_SECONDS || "900");
  const poll = Number(process.env.APPROVAL_POLL_SECONDS || "2");
  const proposed = await q("SELECT line_number, decision, plan_paid_cents, patient_resp_cents FROM agent.decisions WHERE claim_id = $1 ORDER BY line_number", [a.claim_id]);
  const payload = JSON.stringify({ summary: a.summary, reason: a.reason ?? "adverse_or_above_threshold", proposed });

  const existing = await one("SELECT id, status FROM agent.approvals WHERE idempotency_key = $1", [a.claim_id]);
  let approvalId: string;
  if (existing && existing.status !== "pending") return reviewResult(existing.id);
  if (existing) approvalId = existing.id;
  else {
    approvalId = crypto.randomUUID();
    await q("INSERT INTO agent.approvals (id, claim_id, action, payload, idempotency_key) VALUES ($1,$2,'claim_review',$3::jsonb,$4)", [approvalId, a.claim_id, payload, a.claim_id]);
  }
  let waited = 0;
  while (waited < timeout) {
    const status = (await one("SELECT status FROM agent.approvals WHERE id = $1", [approvalId]))?.status;
    if (status && status !== "pending") return reviewResult(approvalId);
    await new Promise((r) => setTimeout(r, poll * 1000));
    waited += poll;
  }
  return { status: "timeout", approval_id: approvalId, waited_seconds: waited };
}

// ── 12. post_adjudication ─────────────────────────────────────────────────────
const STATUS_MAP: Record<string, string> = { pay: "paid", reduce: "reduced", deny: "denied", pend: "pended" };
async function payer_post_adjudication(a: Json): Promise<Json> {
  const decisions = await q("SELECT * FROM agent.decisions WHERE claim_id = $1 ORDER BY line_number", [a.claim_id]);
  if (decisions.length === 0) return { error: "no_decisions", claim_id: a.claim_id };
  const appr = await one("SELECT * FROM agent.approvals WHERE idempotency_key = $1", [a.claim_id]);
  if (appr && appr.status === "pending") return { error: "review_pending", claim_id: a.claim_id, approval_id: appr.id };
  const overrides = (appr && appr.line_overrides) || {};

  const client = await pool().connect();
  const posted: Json[] = [];
  try {
    await client.query("BEGIN");
    for (const d of decisions) {
      const ov = overrides[String(d.line_number)] || {};
      const decision = ov.decision ?? d.decision;
      const planPaid = ov.plan_paid_cents ?? d.plan_paid_cents;
      const patientResp = ov.patient_resp_cents ?? d.patient_resp_cents;
      const status = STATUS_MAP[decision] ?? "pended";
      await client.query(
        `UPDATE ext.claim_lines SET status=$1, allowed_cents=$2, plan_paid_cents=$3, patient_resp_cents=$4,
           carc=$5::jsonb, rarc=$6::jsonb WHERE claim_id=$7 AND line_number=$8`,
        [status, d.allowed_cents, planPaid, patientResp, JSON.stringify(d.carc ?? []), JSON.stringify(d.rarc ?? []), a.claim_id, d.line_number],
      );
      await client.query("UPDATE agent.decisions SET status='final', decided_at=now(), approver=$1 WHERE claim_id=$2 AND line_number=$3", [appr?.decided_by ?? null, a.claim_id, d.line_number]);
      posted.push({ line_number: d.line_number, status, plan_paid_cents: planPaid, patient_resp_cents: patientResp });
    }
    const statuses = new Set(posted.map((p) => p.status));
    const claimStatus = statuses.has("pended") ? "pended" : statuses.size === 1 && statuses.has("denied") ? "denied" : "adjudicated";
    await client.query("UPDATE ext.claims SET status=$1 WHERE id=$2", [claimStatus, a.claim_id]);
    await client.query("COMMIT");
    return {
      claim_id: a.claim_id, claim_status: claimStatus, lines_posted: posted.length, lines: posted,
      total_plan_paid_cents: posted.reduce((s, p) => s + (p.plan_paid_cents || 0), 0),
      total_patient_resp_cents: posted.reduce((s, p) => s + (p.patient_resp_cents || 0), 0),
    };
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}

// ── dispatch + raw Messages API tool definitions ──────────────────────────────
export const DISPATCH: Record<string, (a: Json) => Promise<Json>> = {
  payer_get_agent_provenance, payer_get_claim, payer_get_member_coverage, payer_get_benefit_rules,
  payer_get_accumulators, payer_get_claim_history, payer_check_network, payer_get_allowed_amount,
  payer_lookup_reason_code, payer_adjudicate_line, payer_record_decision, payer_request_review,
  payer_post_adjudication,
};

const S = { type: "string" as const };
const I = { type: "integer" as const };
const SARR = { type: "array" as const, items: { type: "string" as const } };
const obj = (properties: Json, required: string[] = []) => ({ type: "object" as const, properties, required });

export const TOOL_DEFS = [
  { name: "payer_get_agent_provenance", description: "Return the canonical prompt_version_hash (sha256 over CLAUDE.md).", input_schema: obj({}) },
  { name: "payer_get_claim", description: "Fetch the 837 claim: header + lines + diagnosis + attachment refs (heavy).", input_schema: obj({ claim_id: S }, ["claim_id"]) },
  { name: "payer_get_member_coverage", description: "Member eligibility, effective dates, and the plan benefit design.", input_schema: obj({ member_id: S }, ["member_id"]) },
  { name: "payer_get_benefit_rules", description: "Per-code coverage %, frequency, waiting, preauth, category. Pass procedure_codes for this claim's codes only.", input_schema: obj({ plan_id: S, procedure_codes: SARR }, ["plan_id"]) },
  { name: "payer_get_accumulators", description: "Deductible met, annual max used, OOP met for the plan year.", input_schema: obj({ member_id: S, plan_year: I }, ["member_id", "plan_year"]) },
  { name: "payer_get_claim_history", description: "Prior adjudicated lines for frequency/duplicate checks (heavy). Slice with procedure_code.", input_schema: obj({ member_id: S, procedure_code: S, window_days: I }, ["member_id"]) },
  { name: "payer_check_network", description: "In / out of network for (provider, plan).", input_schema: obj({ provider_id: S, plan_id: S }, ["provider_id", "plan_id"]) },
  { name: "payer_get_allowed_amount", description: "Fee-schedule allowed amounts for the codes on the claim.", input_schema: obj({ plan_id: S, procedure_codes: SARR }, ["plan_id", "procedure_codes"]) },
  { name: "payer_lookup_reason_code", description: "CARC / RARC description. Select from these; never invent a code.", input_schema: obj({ code: S }, ["code"]) },
  { name: "payer_adjudicate_line", description: "Run the DETERMINISTIC engine on one line; returns the money + evidence handles.", input_schema: obj({ claim_id: S, line_number: I }, ["claim_id", "line_number"]) },
  { name: "payer_record_decision", description: "Persist proposed per-line decisions with evidence. lines is a list of per-line decision objects.", input_schema: obj({ claim_id: S, model_version: S, prompt_version_hash: S, lines: { type: "array", items: { type: "object" } } }, ["claim_id", "model_version", "prompt_version_hash", "lines"]) },
  { name: "payer_request_review", description: "Open the human review gate; BLOCKS until a claims examiner resolves it.", input_schema: obj({ claim_id: S, summary: S, reason: S }, ["claim_id", "summary"]) },
  { name: "payer_post_adjudication", description: "Commit final decisions to ext.claim_lines (the 835/EOB). Idempotent per line.", input_schema: obj({ claim_id: S }, ["claim_id"]) },
];
