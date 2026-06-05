---
name: intake-and-validate
description: >-
  Parse the claim, confirm member eligibility and effective dates, confirm the
  provider network status, and check the claim is complete. The clean-claim gate:
  missing required data pends with CARC 16 rather than guessing. Use at the start
  of every claim adjudication, before coverage rules.
allowed-tools:
  - mcp__mimic-payer__payer_get_claim
  - mcp__mimic-payer__payer_get_member_coverage
  - mcp__mimic-payer__payer_check_network
---

# Intake & validate

Assemble and sanity-check the claim before any adjudication.

1. **Claim** — `payer_get_claim(claim_id)`. Note `member_id`, `provider_id`, the
   service `lines` (line_number, procedure_code, tooth/surface, date_of_service,
   units, charged_cents, preauth_number), `diagnosis_codes`, and the
   `total_charged_cents`. The claim is large — the `attachment_bodies` are bulky
   clinical detail you do **not** read unless a specific line needs clinical
   review.
2. **Coverage** — `payer_get_member_coverage(member_id)`. Confirm the member is
   `active`, that the service dates fall on/after `effective_date` and before any
   `term_date`, and capture the `plan` (id, type, deductible, annual max,
   coinsurance design).
3. **Network** — `payer_check_network(provider_id, plan_id)`. Record
   `in_network`; an out-of-network provider drives a reduction later.

**Clean-claim gate.** If a line is missing data the rule needs — e.g. a required
tooth/surface for a dental restorative code, or an attachment the benefit rule
requires — do not guess. That line **pends with CARC 16** (claim/service lacks
information). Likewise, if the member is termed or the service predates coverage,
the affected lines are not payable.

Never fabricate values; if a tool returns an error, stop and report it. Do not
proceed to coverage rules until the claim, coverage, and network are retrieved.
