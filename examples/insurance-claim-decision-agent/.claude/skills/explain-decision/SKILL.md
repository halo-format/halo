---
name: explain-decision
description: >-
  Produce the EOB-style rationale for an adjudicated claim, citing the rule and the
  evidence for each line. Use as the final step, after the adjudication is posted.
---

# Explain decision

Produce an explanation a member or an auditor could read — the
Explanation-of-Benefits view of what you decided and why.

For each line, state:

- the procedure code and the **decision** (paid / denied / reduced / pended);
- the **money**: allowed, plan paid, patient responsibility, and the split
  (deductible / coinsurance) — exactly as the engine returned it;
- the **reason codes** (CARC group + code and the RARC), with the plain-language
  description from `payer_lookup_reason_code`;
- the **rule basis**: which benefit rule or check drove it (e.g. "major service
  at 50%", "annual maximum reached", "preauth absent", "non-covered cosmetic").

Then give the claim-level summary: total plan paid, total patient responsibility,
the claim status, and — if it went to review — who resolved it and whether it was
an override.

Close with the **evidence**: the decision rests on the content-addressed handles
recorded in `agent.decisions.evidence`. Because handles are content hashes and the
store re-verifies on read, that is a tamper-evident record of the exact data the
decision used — which is what an appeal or a regulatory review needs. Do not
restate the bulky clinical attachments; cite the handles.
