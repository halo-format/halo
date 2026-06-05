---
name: adjudicate
description: >-
  Call the deterministic engine per line for the money, attach the reason codes
  selected from the reference set, classify each line pay/deny/reduce/pend, record
  the decisions with evidence, and route any adverse or above-ceiling outcome
  through the human review gate. Use as the decision step of every claim.
allowed-tools:
  - mcp__mimic-payer__payer_adjudicate_line
  - mcp__mimic-payer__payer_lookup_reason_code
  - mcp__mimic-payer__payer_get_agent_provenance
  - mcp__mimic-payer__payer_record_decision
  - mcp__mimic-payer__payer_request_review
  - mcp__mimic-payer__payer_post_adjudication
---

# Adjudicate

## 1. Run the engine per line (you never compute money)

For each line call `payer_adjudicate_line(claim_id, line_number)`. It returns the
amounts (`allowed_cents`, `plan_paid_cents`, `patient_resp_cents`,
`deductible_cents`, `coinsurance_cents`), `suggested_carc` / `suggested_rarc`, a
`review_required` flag with `review_reasons`, and the `evidence` handles of the
exact data it used. Use those numbers verbatim.

## 2. Classify the line

```
pay     covered, in network, within limits, no anomaly
        (normal deductible / coinsurance is still pay)
reduce  review_required for out_of_network or annual_max_reached
        (plan pays less than its normal benefit)
deny    not_covered                         → CARC 96
pend    a check from coverage-and-rules failed:
        missing preauth (197) | duplicate (18) | frequency (119) |
        waiting period (26) | missing information (16)
```

For a **pend** or **deny**, record `plan_paid_cents` and `patient_resp_cents` as
**0**. For **pay** / **reduce**, use the engine's amounts.

## 3. Select reason codes — never invent

Every CARC/RARC you attach must come from the reference set. Confirm each with
`payer_lookup_reason_code(code)` before using it.

## 4. Record with evidence

Call `payer_get_agent_provenance` and keep `prompt_version_hash`. Then
`payer_record_decision(claim_id, model_version, prompt_version_hash, lines[])`,
each line carrying `decision`, the amounts, `carc`/`rarc`, a `rule_basis` (which
checks fired), and the `evidence` handles from `payer_adjudicate_line`. The tool
returns `requires_human`.

## 5. Human review (humans own denials, reductions, pends)

If `requires_human` is true, call `payer_request_review(claim_id, summary)`. **It
blocks** until a claims examiner resolves it:

- `confirmed` → the proposed adjudication stands.
- `modified` → apply the examiner's `line_overrides`.
- `rejected` → the lines are denied.
- `is_override = true` → the examiner went against your proposal (the appeal /
  audit evidence).

## 6. Post

Call `payer_post_adjudication(claim_id)` to commit the final per-line decisions to
`ext.claim_lines` (the 835/EOB). It is idempotent per (claim_id, line_number).
Only after the human has resolved the review may an adverse outcome be finalized.
