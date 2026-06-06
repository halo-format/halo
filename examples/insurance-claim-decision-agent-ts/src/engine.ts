// ============================================================================
// The deterministic adjudication engine — the money, computed by fixed code.
//
//   The model orchestrates and reasons. A deterministic engine computes the money.
//
// adjudicateLine is pure arithmetic + fixed rule application: fee schedule →
// deductible → coinsurance (with the out-of-network penalty) → annual-maximum
// cap. No model. It returns the amounts, the suggested CARCs that explain each
// adjustment, and review_required/review_reasons; the agent maps that to a
// per-line decision (pay / deny / reduce / pend). A direct port of engine.py —
// same rules, same numbers.
// ============================================================================

// Points of coinsurance withheld when the rendering provider is out of network.
export const OON_PENALTY_POINTS = 20;

export interface LineResult {
  allowed_cents: number;
  plan_paid_cents: number;
  patient_resp_cents: number;
  deductible_cents: number;
  coinsurance_cents: number;
  copay_cents: number;
  disallowed_cents: number;
  suggested_carc: { code: string; group: string }[];
  suggested_rarc: string[];
  review_required: boolean;
  review_reasons: string[];
  computed_by: "engine";
}

export interface EngineInputs {
  line: { procedure_code: string; units: number; charged_cents: number };
  rule: { covered?: boolean; coverage_pct?: number };
  accumulators: { deductible_met_cents: number; annual_max_used_cents: number };
  allowed_cents: number; // fee-schedule allowed amount per unit
  network: { in_network: boolean };
  plan: { deductible_cents: number; annual_max_cents: number };
}

export function adjudicateLine(i: EngineInputs): LineResult {
  const units = i.line.units || 1;
  const charged = i.line.charged_cents;

  // ── Non-covered: nothing to compute. Plan pays 0; routed to a human. ──────
  if (!i.rule.covered) {
    return {
      allowed_cents: 0, plan_paid_cents: 0, patient_resp_cents: 0,
      deductible_cents: 0, coinsurance_cents: 0, copay_cents: 0,
      disallowed_cents: charged,
      suggested_carc: [{ code: "96", group: "CO" }], // Non-covered charge(s)
      suggested_rarc: [],
      review_required: true, review_reasons: ["not_covered"], computed_by: "engine",
    };
  }

  const carc: { code: string; group: string }[] = [];
  const rarc: string[] = [];
  const reviewReasons: string[] = [];

  // 1. Fee schedule: allowed is the lesser of charged and the contracted rate.
  const feeAllowed = i.allowed_cents * units;
  const allowed = Math.min(charged, feeAllowed);
  const disallowed = charged - allowed;
  if (disallowed > 0) carc.push({ code: "45", group: "CO" }); // exceeds fee schedule

  // 2. Deductible.
  const dedRemaining = Math.max(0, i.plan.deductible_cents - i.accumulators.deductible_met_cents);
  const deductible = Math.min(allowed, dedRemaining);
  const afterDeductible = allowed - deductible;
  if (deductible > 0) carc.push({ code: "1", group: "PR" }); // Deductible amount

  // 3. Coinsurance. Coverage % from the per-code rule; OON penalty if out of network.
  let coveragePct = i.rule.coverage_pct || 0;
  const outOfNetwork = !i.network.in_network;
  if (outOfNetwork) {
    coveragePct = Math.max(0, coveragePct - OON_PENALTY_POINTS);
    reviewReasons.push("out_of_network");
  }
  const planShare = Math.round((afterDeductible * coveragePct) / 100);
  const coinsurance = afterDeductible - planShare;
  if (coinsurance > 0) carc.push({ code: "2", group: "PR" }); // Coinsurance amount
  if (outOfNetwork) {
    carc.push({ code: "242", group: "PI" }); // not provided by network providers
    rarc.push("N130");
  }

  // 4. Annual maximum cap. The plan never pays past the remaining benefit.
  const annualRemaining = Math.max(0, i.plan.annual_max_cents - i.accumulators.annual_max_used_cents);
  let overMax = 0;
  let planPaid: number;
  if (planShare > annualRemaining) {
    overMax = planShare - annualRemaining;
    planPaid = annualRemaining;
    carc.push({ code: "119", group: "PR" }); // Benefit maximum reached
    rarc.push("N362");
    reviewReasons.push("annual_max_reached");
  } else {
    planPaid = planShare;
  }

  const patientResp = deductible + coinsurance + overMax;
  return {
    allowed_cents: allowed, plan_paid_cents: planPaid, patient_resp_cents: patientResp,
    deductible_cents: deductible, coinsurance_cents: coinsurance, copay_cents: 0,
    disallowed_cents: disallowed, suggested_carc: carc, suggested_rarc: rarc,
    review_required: reviewReasons.length > 0, review_reasons: reviewReasons, computed_by: "engine",
  };
}

/** Reference mapping from an engine result (+ agent-judged pends) to a decision. */
export function classify(result: LineResult, pendReasons: string[] = []): string {
  if (pendReasons.length > 0) return "pend";
  if (result.review_reasons.includes("not_covered")) return "deny";
  if (result.review_required) return "reduce"; // out_of_network / annual_max_reached
  return "pay";
}
