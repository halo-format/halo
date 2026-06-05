---
name: coverage-and-rules
description: >-
  For each line, gather the benefit rule, fee schedule, accumulators, and claim
  history, and judge which rules apply — including the edge cases the deterministic
  engine cannot resolve alone (preauth, frequency, waiting period, duplicate). Use
  after intake, before adjudicating.
allowed-tools:
  - mcp__mimic-payer__payer_get_benefit_rules
  - mcp__mimic-payer__payer_get_allowed_amount
  - mcp__mimic-payer__payer_get_accumulators
  - mcp__mimic-payer__payer_get_claim_history
---

# Coverage & rules

Gather the per-line decision inputs and judge applicability. Fetch only what this
claim needs — never the whole plan.

1. **Benefit rules** — `payer_get_benefit_rules(plan_id, procedure_codes)` for the
   **codes on this claim only**. For each code note `covered`, `coverage_pct`,
   `category`, `frequency_limit`, `waiting_months`, `requires_preauth`.
2. **Allowed amounts** — `payer_get_allowed_amount(plan_id, procedure_codes)`.
3. **Accumulators** — `payer_get_accumulators(member_id, plan_year)` where
   `plan_year` is the service year. Note deductible met, annual max used, OOP met.
4. **History** — `payer_get_claim_history(member_id, procedure_code)` for the
   codes that have a frequency limit or a duplicate risk. Slice by code; do not
   pull the member's whole history into context.

## Judge the edge cases (these become *pends*, not auto-denials)

The engine handles fee schedule, deductible, coinsurance, network, and annual
max. **You** judge the history- and claim-data-dependent rules:

- **Missing preauth** — `requires_preauth` is true and the line has no
  `preauth_number` → pend, CARC 197 (+ RARC N705).
- **Duplicate** — the same code on the same `date_of_service` already appears in
  history → pend, CARC 18.
- **Frequency** — prior paid lines for the code in the limit window meet or exceed
  `frequency_limit` → pend (CARC 119, RARC N362).
- **Waiting period** — `effective_date` + `waiting_months` is after the service
  date → pend (CARC 26).
- **Missing information** — a required field is absent → pend, CARC 16.

Carry the rule and the history finding forward; the adjudicate skill turns the
engine numbers plus these judgments into the per-line decision. Quote exact
amounts and never round away cents.
