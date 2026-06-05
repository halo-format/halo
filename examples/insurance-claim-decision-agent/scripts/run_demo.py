"""End-to-end demo: one claim adjudicated line by line, then human-reviewed.

Drives the REAL `mimic-payer` MCP tools (no LLM / API key required) through the
full flow for the seeded demo claim — intake, coverage rules, the DETERMINISTIC
engine per line, record, the blocking human review gate (auto-confirmed by a
stand-in examiner), and post to ext.claim_lines (the 835/EOB). Useful as a
deterministic smoke test of the environment + MCP server + engine.

    python -m scripts.run_demo [CLAIM_ID]

The live, model-driven version is `python -m agent.main`.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("APPROVAL_POLL_SECONDS", "1")
os.environ.setdefault("APPROVAL_TIMEOUT_SECONDS", "60")

from agent.prompts import MODEL_VERSION, PROMPT_VERSION_HASH  # noqa: E402
from mcp_servers.mimic_payer import server as S  # noqa: E402
from scripts.reviewer_console import resolve  # noqa: E402

DEMO_CLAIM = "CLM-1001"


def _classify(eng: dict, pend_reasons: list[str]) -> str:
    if pend_reasons:
        return "pend"
    if "not_covered" in eng.get("review_reasons", []):
        return "deny"
    if eng.get("review_required"):
        return "reduce"
    return "pay"


def _d(cents: int) -> str:
    return f"${cents / 100:,.2f}"


async def _approval_id_for(claim_id: str) -> str:
    import asyncpg
    from scripts.reviewer_console import _admin_dsn

    conn = await asyncpg.connect(_admin_dsn())
    try:
        for _ in range(60):
            row = await conn.fetchrow(
                "SELECT id FROM agent.approvals WHERE claim_id = $1 AND status='pending' "
                "ORDER BY created_at DESC LIMIT 1", claim_id
            )
            if row:
                return str(row["id"])
            await asyncio.sleep(0.5)
    finally:
        await conn.close()
    raise RuntimeError("approval row never appeared")


async def main(claim_id: str) -> None:
    print(f"=== Insurance Claim Decision Agent — deterministic demo — {claim_id} ===\n")

    # 1. Intake + validate
    claim = await S.payer_get_claim(claim_id)
    cov = await S.payer_get_member_coverage(claim["member_id"])
    net = await S.payer_check_network(claim["provider_id"], cov["plan"]["id"])
    member, plan = cov["member"], cov["plan"]
    print(f"Member   : {member['first_name']} {member['last_name']}  plan {plan['id']} ({plan['type']})")
    print(f"Provider : {claim['provider_id']}  in_network={net['in_network']}")
    print(f"Claim    : {len(claim['lines'])} lines, charged {_d(claim['total_charged_cents'])}\n")

    # 2. Coverage + rules
    codes = [ln["procedure_code"] for ln in claim["lines"]]
    rules = {r["procedure_code"]: r
             for r in (await S.payer_get_benefit_rules(plan["id"], codes))["rules"]}
    history = (await S.payer_get_claim_history(claim["member_id"]))["lines"]
    prov = await S.payer_get_agent_provenance()

    # 3. Adjudicate each line with the deterministic engine; the model-side logic
    #    here only classifies and judges history-dependent pends.
    line_decisions = []
    for ln in claim["lines"]:
        code = ln["procedure_code"]
        rule = rules.get(code, {})
        eng = await S.payer_adjudicate_line(claim_id, ln["line_number"])

        pend_reasons = []
        if rule.get("requires_preauth") and not ln.get("preauth_number"):
            pend_reasons.append("missing_preauth")
        if any(h["procedure_code"] == code and h["date_of_service"] == ln["date_of_service"]
               for h in history):
            pend_reasons.append("duplicate")

        decision = _classify(eng, pend_reasons)

        if decision == "pend":
            carc = [{"code": "197", "group": "CO"}] if "missing_preauth" in pend_reasons \
                else [{"code": "18", "group": "OA"}]
            rarc = ["N705"] if "missing_preauth" in pend_reasons else []
            plan_paid = patient = ded = coins = 0
        elif decision == "deny":
            carc, rarc = eng["suggested_carc"], eng["suggested_rarc"]
            plan_paid = patient = ded = coins = 0
        else:  # pay / reduce
            carc, rarc = eng["suggested_carc"], eng["suggested_rarc"]
            plan_paid = eng["plan_paid_cents"]
            patient = eng["patient_resp_cents"]
            ded = eng["deductible_cents"]
            coins = eng["coinsurance_cents"]

        line_decisions.append({
            "line_number": ln["line_number"], "decision": decision,
            "allowed_cents": eng["allowed_cents"], "plan_paid_cents": plan_paid,
            "patient_resp_cents": patient, "deductible_cents": ded, "coinsurance_cents": coins,
            "copay_cents": 0, "carc": carc, "rarc": rarc,
            "rule_basis": (eng["review_reasons"] + pend_reasons +
                           [f"coverage_pct={rule.get('coverage_pct')}"]),
            "evidence": list(eng["evidence"].values()),
            "rationale": f"{code}: {decision} ({', '.join(eng['review_reasons'] + pend_reasons) or 'clean'})",
        })
        print(f"  line {ln['line_number']} {code:<6} → {decision.upper():<7} "
              f"plan_paid {_d(plan_paid)}  patient {_d(patient)}  carc {[c['code'] for c in carc]}")

    # 4. Record (proposed) with evidence handles
    rec = await S.payer_record_decision(
        claim_id=claim_id, model_version=MODEL_VERSION,
        prompt_version_hash=prov["prompt_version_hash"], lines=line_decisions,
    )
    print(f"\nRecorded {rec['lines_recorded']} decisions  requires_human={rec['requires_human']} "
          f"({rec['reason']})")

    # 5. Human review gate (auto-confirmed by a stand-in examiner) if required
    if rec["requires_human"]:
        print("\nOpening human review gate (agent now blocks)…")
        summary = (f"Claim {claim_id}: mixed outcomes incl. reduce/pend/deny and total above the "
                   f"auto-finalize ceiling. Recommend confirm as proposed.")
        gate = asyncio.create_task(S.payer_request_review(claim_id=claim_id, summary=summary))

        async def examiner():
            approval_id = await _approval_id_for(claim_id)
            await asyncio.sleep(1)
            print("  [examiner] reviewing proposed adjudication… confirming as proposed")
            await resolve(approval_id=approval_id, action="confirm", decided_by="ex-204-rkhan",
                          justification="Reduction is the annual-max cap; pend awaits preauth; "
                                        "denial is the non-covered cosmetic line. Confirmed.")

        ex_task = asyncio.create_task(examiner())
        review = await gate
        await ex_task
        print(f"\nReview resolved: status={review['status']}  is_override={review['is_override']}  "
              f"by {review['decided_by']}")
    else:
        print("\nAll lines clean and below ceiling — auto-finalize, no human gate.")

    # 6. Post the adjudication (the 835/EOB) — idempotent per line
    posted = await S.payer_post_adjudication(claim_id)
    print(f"\nPosted to ext.claim_lines — claim status '{posted['claim_status']}'")
    print(f"  plan paid total    : {_d(posted['total_plan_paid_cents'])}")
    print(f"  patient resp total : {_d(posted['total_patient_resp_cents'])}")
    for p in posted["lines"]:
        print(f"    line {p['line_number']}: {p['status']:<8} plan_paid {_d(p['plan_paid_cents'])}  "
              f"patient {_d(p['patient_resp_cents'])}")
    print("\n=== demo complete ===")


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else DEMO_CLAIM
    asyncio.run(main(cid))
