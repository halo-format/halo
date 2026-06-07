"""The deterministic adjudication engine.

This is the rule from the architecture made literal:

    The model orchestrates and reasons. A deterministic engine computes the money.

``adjudicate_line`` is pure arithmetic and fixed rule application — no LLM, no
network, reproducible. The model never lands here; it only decides *which* line
to adjudicate and *which* reason code to attach from the reference set. The
amounts, and the suggested CARCs that explain them, come from this code.

It returns the money plus ``review_required`` / ``review_reasons``: the engine
surfaces an anomaly (out-of-network penalty, annual-maximum cap, non-covered),
and the *model* maps that to a per-line decision (pay / deny / reduce / pend)
using the ``adjudicate`` skill. History-dependent pends (duplicate, frequency,
waiting period, missing preauth, missing information) are judged one level up,
by the agent, because they need data the engine is not handed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Points of coinsurance withheld when the rendering provider is out of network.
# A real plan reads this from the benefit design; fixed here for a reproducible demo.
OON_PENALTY_POINTS = 20


@dataclass
class LineResult:
    allowed_cents: int
    plan_paid_cents: int
    patient_resp_cents: int
    deductible_cents: int
    coinsurance_cents: int
    copay_cents: int
    disallowed_cents: int
    suggested_carc: list[dict[str, str]] = field(default_factory=list)
    suggested_rarc: list[str] = field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    computed_by: str = "engine"

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed_cents": self.allowed_cents,
            "plan_paid_cents": self.plan_paid_cents,
            "patient_resp_cents": self.patient_resp_cents,
            "deductible_cents": self.deductible_cents,
            "coinsurance_cents": self.coinsurance_cents,
            "copay_cents": self.copay_cents,
            "disallowed_cents": self.disallowed_cents,
            "suggested_carc": self.suggested_carc,
            "suggested_rarc": self.suggested_rarc,
            "review_required": self.review_required,
            "review_reasons": self.review_reasons,
            "computed_by": self.computed_by,
        }


def adjudicate_line(
    *,
    line: dict[str, Any],
    rule: dict[str, Any],
    accumulators: dict[str, Any],
    allowed_cents: int,
    network: dict[str, Any],
    plan: dict[str, Any],
) -> LineResult:
    """Compute the 835/EOB money for one service line. Deterministic.

    ``line``         : { procedure_code, units, charged_cents }
    ``rule``         : { covered, coverage_pct, category, ... }
    ``accumulators`` : { deductible_met_cents, annual_max_used_cents, ... }
    ``allowed_cents``: fee-schedule allowed amount for the code (per unit)
    ``network``      : { in_network }
    ``plan``         : { deductible_cents, annual_max_cents, coinsurance, ... }
    """
    units = int(line.get("units") or 1)
    charged = int(line["charged_cents"])

    # ── Non-covered: nothing to compute. Plan pays 0; routed to a human. ──────
    if not rule.get("covered", False):
        return LineResult(
            allowed_cents=0,
            plan_paid_cents=0,
            patient_resp_cents=0,
            deductible_cents=0,
            coinsurance_cents=0,
            copay_cents=0,
            disallowed_cents=charged,
            suggested_carc=[{"code": "96", "group": "CO"}],  # Non-covered charge(s)
            review_required=True,
            review_reasons=["not_covered"],
        )

    carc: list[dict[str, str]] = []
    rarc: list[str] = []
    review_reasons: list[str] = []

    # 1. Fee schedule: allowed is the lesser of charged and the contracted rate.
    fee_allowed = int(allowed_cents) * units
    allowed = min(charged, fee_allowed)
    disallowed = charged - allowed
    if disallowed > 0:
        carc.append({"code": "45", "group": "CO"})  # exceeds fee schedule (provider write-off)

    # 2. Deductible (member's responsibility before the plan shares).
    ded_remaining = max(0, int(plan["deductible_cents"]) - int(accumulators["deductible_met_cents"]))
    deductible = min(allowed, ded_remaining)
    after_deductible = allowed - deductible
    if deductible > 0:
        carc.append({"code": "1", "group": "PR"})  # Deductible amount

    # 3. Coinsurance. Coverage % from the per-code rule (the plan's benefit design).
    coverage_pct = int(rule.get("coverage_pct", 0))
    out_of_network = not bool(network.get("in_network", True))
    if out_of_network:
        coverage_pct = max(0, coverage_pct - OON_PENALTY_POINTS)
        review_reasons.append("out_of_network")

    plan_share = round(after_deductible * coverage_pct / 100)
    coinsurance = after_deductible - plan_share
    if coinsurance > 0:
        carc.append({"code": "2", "group": "PR"})  # Coinsurance amount
    if out_of_network:
        carc.append({"code": "242", "group": "PI"})  # not provided by network providers
        rarc.append("N130")

    # 4. Annual maximum cap. The plan never pays past the remaining benefit.
    annual_remaining = max(
        0, int(plan["annual_max_cents"]) - int(accumulators["annual_max_used_cents"])
    )
    over_max = 0
    if plan_share > annual_remaining:
        over_max = plan_share - annual_remaining
        plan_paid = annual_remaining
        carc.append({"code": "119", "group": "PR"})  # Benefit maximum reached
        rarc.append("N362")
        review_reasons.append("annual_max_reached")
    else:
        plan_paid = plan_share

    copay = 0
    patient_resp = deductible + coinsurance + over_max

    return LineResult(
        allowed_cents=allowed,
        plan_paid_cents=plan_paid,
        patient_resp_cents=patient_resp,
        deductible_cents=deductible,
        coinsurance_cents=coinsurance,
        copay_cents=copay,
        disallowed_cents=disallowed,
        suggested_carc=carc,
        suggested_rarc=rarc,
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
    )


def classify(result: LineResult, *, pend_reasons: list[str] | None = None) -> str:
    """Reference mapping from an engine result (+ agent-judged pends) to a decision.

    The live agent applies the same mapping via the ``adjudicate`` skill; the
    deterministic demo calls this directly so the two paths agree.
    """
    pend_reasons = pend_reasons or []
    if pend_reasons:
        return "pend"
    if "not_covered" in result.review_reasons:
        return "deny"
    if result.review_required:  # out_of_network / annual_max_reached
        return "reduce"
    return "pay"
