"""mimic-payer MCP server.

Domain-shaped tools over the simulated ``mimic_payer`` Postgres (schemas ``ext.*``
= the payer mirror, ``agent.*`` = the agent's own state). Transport: stdio — run
with ``python -m mcp_servers.mimic_payer.server``. Inputs are Pydantic-validated;
tools return JSON-safe dicts.

The contract is the swap point: SQL on ``ext.*`` today, real payer feeds later.
Three properties are load-bearing and enforced here, not left to the model:

  * ``payer_adjudicate_line`` runs the DETERMINISTIC engine on inputs it fetches
    itself — the model never supplies or computes an amount.
  * Every adjudication input the engine touched is written to the content-addressed
    store (``agent.halo_nodes``) and its handle is recorded as the decision's
    evidence — a tamper-evident record of exactly what the decision rested on.
  * ``payer_request_review`` BLOCKS the run until a human resolves the gate, and
    ``payer_post_adjudication`` is idempotent per (claim_id, line_number), so a
    retry cannot pay twice.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import db
from .engine import adjudicate_line as engine_adjudicate
from .models import (
    AdjudicateLineIn,
    CheckNetworkIn,
    GetAccumulatorsIn,
    GetAllowedAmountIn,
    GetBenefitRulesIn,
    GetClaimHistoryIn,
    GetClaimIn,
    GetMemberCoverageIn,
    LookupReasonCodeIn,
    PostAdjudicationIn,
    RecordDecisionIn,
    RequestReviewIn,
)

mcp = FastMCP("mimic-payer")

# Claims at or below this charged amount, with every line a clean "pay", can
# auto-finalize. Anything above it goes to a human even if all lines pay.
AUTO_FINALIZE_MAX_CENTS = int(os.environ.get("AUTO_FINALIZE_MAX_CENTS", "50000"))


# ── content-addressing for the evidence store ────────────────────────────────
# Prefer halo_format's own canonicalization so an evidence handle is byte-identical
# to the handle Halo would navigate by; fall back to a compact JSON hash if the
# core package is not installed (the baseline run needs nothing extra).
try:  # pragma: no cover - exercised by whichever path is installed
    from halo_format import canonical_bytes as _canonical_bytes
    from halo_format import handle_of as _handle_of

    _HANDLE_SCHEME = "halo"
except Exception:  # pragma: no cover
    def _canonical_bytes(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _handle_of(value: Any) -> str:
        return "h:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()

    _HANDLE_SCHEME = "fallback"


# ── serialisation helpers ────────────────────────────────────────────────────
def _jsonify(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _row(record: Any) -> dict[str, Any] | None:
    return _jsonify(dict(record)) if record is not None else None


def _loads(value: Any) -> Any:
    """asyncpg returns jsonb columns as strings; decode them."""
    return json.loads(value) if isinstance(value, str) else value


async def _put_node(conn: Any, value: Any) -> str:
    """Write a value into the content-addressed store and return its handle.

    The handle IS the integrity proof: every read re-hashes the bytes before use,
    so the recorded evidence is tamper-evident.
    """
    handle = _handle_of(value)
    await conn.execute(
        "INSERT INTO agent.halo_nodes (handle, bytes) VALUES ($1, $2) "
        "ON CONFLICT (handle) DO NOTHING",
        handle,
        _canonical_bytes(value),
    )
    return handle


# ── canonical prompt provenance (CLAUDE.md governs every runtime) ────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CLAUDE_MD = _PROJECT_ROOT / "CLAUDE.md"
_FALLBACK_PROMPT = b"You are the Insurance Claim Decision Agent. Act only through the mimic-payer MCP tools."


def _prompt_version_hash() -> str:
    try:
        data = _CLAUDE_MD.read_bytes()
    except OSError:
        data = _FALLBACK_PROMPT
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ── 0. get_agent_provenance ──────────────────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get canonical agent prompt provenance",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_agent_provenance() -> dict[str, Any]:
    """Return the canonical ``prompt_version_hash`` (sha256 over CLAUDE.md).

    Call this before recording a decision and pass the value into
    ``payer_record_decision`` so the audit record pins the exact governing
    instructions, regardless of how the agent was launched (CLI or SDK).
    """
    return {
        "prompt_version_hash": _prompt_version_hash(),
        "prompt_source": "CLAUDE.md",
        "agent_id": "insurance-claim-decision-agent",
        "evidence_handle_scheme": _HANDLE_SCHEME,
    }


# ── 1. get_claim (heavy, Halo-encoded) ───────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get claim header + lines + diagnosis + attachments",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_claim(claim_id: str) -> dict[str, Any]:
    """Fetch the 837 claim: header, service lines, diagnosis, attachment refs.

    Heavy by nature — the attachment bodies (clinical notes / x-ray metadata) are
    several KB the adjudication mostly does not read, which is exactly the payload
    Halo keeps out of the model's context until a line needs clinical review.
    """
    GetClaimIn(claim_id=claim_id)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        claim = await conn.fetchrow("SELECT * FROM ext.claims WHERE id = $1", claim_id)
        if claim is None:
            return {"error": "claim_not_found", "claim_id": claim_id}
        lines = await conn.fetch(
            "SELECT * FROM ext.claim_lines WHERE claim_id = $1 ORDER BY line_number", claim_id
        )
    out = _row(claim)
    out["diagnosis_codes"] = _loads(out.get("diagnosis_codes"))
    out["attachments"] = _loads(out.get("attachments"))
    out["lines"] = [_row(r) for r in lines]
    # Synthesize the bulky clinical attachment bodies the header only references.
    out["attachment_bodies"] = _attachment_bodies(out)
    return out


def _attachment_bodies(claim: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic, bulky per-attachment clinical detail (notes + x-ray meta).

    Seeded from the claim id so the same claim always yields the same bodies.
    The decision reads none of this unless a line is flagged for clinical review.
    """
    refs = claim.get("attachments") or []
    seed = int(hashlib.sha256(str(claim.get("id", "")).encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    bodies = []
    paras = (
        "Patient presents for evaluation. Intraoral examination performed; findings "
        "documented per chart. Radiographic series reviewed. Treatment plan discussed "
        "with patient and consent obtained. No adverse reaction noted during procedure."
    )
    for ref in refs:
        bodies.append(
            {
                "attachment_ref": ref,
                "kind": rng.choice(["clinical_note", "periapical_xray", "bitewing_xray", "perio_chart"]),
                "captured_at": f"2026-0{rng.randint(1, 5)}-{rng.randint(10, 28)}",
                "narrative": " ".join([paras] * rng.randint(2, 4)),
                "tooth_chart": {f"{t}": rng.choice(["sound", "restored", "caries", "missing"]) for t in range(1, 33)},
                "image_meta": {"dpi": 300, "bytes": rng.randint(180000, 920000), "modality": "intraoral"},
            }
        )
    return bodies


# ── 2. get_member_coverage (270/271 later) ───────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get member coverage + plan + eligibility",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_member_coverage(member_id: str) -> dict[str, Any]:
    """Member eligibility, effective dates, and the plan benefit design."""
    GetMemberCoverageIn(member_id=member_id)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        member = await conn.fetchrow("SELECT * FROM ext.members WHERE id = $1", member_id)
        if member is None:
            return {"error": "member_not_found", "member_id": member_id}
        plan = await conn.fetchrow("SELECT * FROM ext.plans WHERE id = $1", member["plan_id"])
    m = _row(member)
    p = _row(plan)
    if p is not None:
        p["coinsurance"] = _loads(p.get("coinsurance"))
    return {"member": m, "plan": p}


# ── 3. get_benefit_rules (whole plan is large; fetch only this claim's codes) ─
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get per-code benefit rules",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_benefit_rules(
    plan_id: str, procedure_codes: list[str] | None = None
) -> dict[str, Any]:
    """Per-code coverage %, frequency, waiting, preauth, category.

    With ``procedure_codes`` omitted this returns the whole plan's rule set —
    large, and exactly what you should NOT pull; pass the codes on the claim.
    """
    args = GetBenefitRulesIn(plan_id=plan_id, procedure_codes=procedure_codes)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        if args.procedure_codes:
            rows = await conn.fetch(
                "SELECT * FROM ext.benefit_rules WHERE plan_id = $1 AND procedure_code = ANY($2::text[])",
                plan_id, args.procedure_codes,
            )
        else:
            rows = await conn.fetch("SELECT * FROM ext.benefit_rules WHERE plan_id = $1", plan_id)
    return {"plan_id": plan_id, "rules": [_row(r) for r in rows]}


# ── 4. get_accumulators ──────────────────────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get member accumulators for the plan year",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_accumulators(member_id: str, plan_year: int) -> dict[str, Any]:
    """Deductible met, annual maximum used, OOP met for the plan year."""
    GetAccumulatorsIn(member_id=member_id, plan_year=plan_year)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rec = await conn.fetchrow(
            "SELECT * FROM ext.accumulators WHERE member_id = $1 AND plan_year = $2",
            member_id, plan_year,
        )
    if rec is None:
        return {
            "member_id": member_id, "plan_year": plan_year,
            "deductible_met_cents": 0, "annual_max_used_cents": 0, "oop_met_cents": 0,
        }
    return _row(rec)


# ── 5. get_claim_history (heavy, Halo) ───────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get prior claim lines for frequency / duplicate checks",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_claim_history(
    member_id: str, procedure_code: str | None = None, window_days: int = 365
) -> dict[str, Any]:
    """Prior adjudicated lines for the member, for frequency and duplicate checks.

    Can be large; with ``procedure_code`` set it slices to the code relevant to the
    check (the Halo-friendly access pattern).
    """
    args = GetClaimHistoryIn(member_id=member_id, procedure_code=procedure_code, window_days=window_days)
    since = dt.date.today() - dt.timedelta(days=args.window_days)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        if args.procedure_code:
            rows = await conn.fetch(
                """SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id = cl.claim_id
                   WHERE c.member_id = $1 AND cl.procedure_code = $2 AND cl.date_of_service >= $3
                   ORDER BY cl.date_of_service DESC""",
                member_id, args.procedure_code, since,
            )
        else:
            rows = await conn.fetch(
                """SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id = cl.claim_id
                   WHERE c.member_id = $1 AND cl.date_of_service >= $2 AND c.status <> 'received'
                   ORDER BY cl.date_of_service DESC""",
                member_id, since,
            )
    history = [_row(r) for r in rows]
    for h in history:
        h["carc"] = _loads(h.get("carc"))
        h["rarc"] = _loads(h.get("rarc"))
    return {"member_id": member_id, "procedure_code": procedure_code, "lines": history}


# ── 6. check_network ─────────────────────────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Check provider network status for a plan",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_check_network(provider_id: str, plan_id: str) -> dict[str, Any]:
    """In / out of network for (provider, plan)."""
    CheckNetworkIn(provider_id=provider_id, plan_id=plan_id)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rec = await conn.fetchrow(
            "SELECT * FROM ext.network WHERE plan_id = $1 AND provider_id = $2", plan_id, provider_id
        )
    if rec is None:
        # No contract on file = out of network.
        return {"plan_id": plan_id, "provider_id": provider_id, "in_network": False, "on_file": False}
    out = _row(rec)
    out["on_file"] = True
    return out


# ── 7. get_allowed_amount ────────────────────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Get fee-schedule allowed amounts",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_get_allowed_amount(plan_id: str, procedure_codes: list[str]) -> dict[str, Any]:
    """Fee-schedule allowed amounts for the codes on the claim."""
    GetAllowedAmountIn(plan_id=plan_id, procedure_codes=procedure_codes)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT procedure_code, allowed_cents FROM ext.fee_schedule "
            "WHERE plan_id = $1 AND procedure_code = ANY($2::text[])",
            plan_id, procedure_codes,
        )
    return {"plan_id": plan_id, "allowed": {r["procedure_code"]: r["allowed_cents"] for r in rows}}


# ── 8. lookup_reason_code ────────────────────────────────────────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Look up a CARC / RARC reason code",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_lookup_reason_code(code: str) -> dict[str, Any]:
    """CARC / RARC description. The agent SELECTS from these; it never invents one."""
    LookupReasonCodeIn(code=code)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rec = await conn.fetchrow("SELECT * FROM ext.reason_codes WHERE code = $1", code)
    if rec is None:
        return {"error": "unknown_reason_code", "code": code}
    return _row(rec)


# ── 9. adjudicate_line (DETERMINISTIC engine, not an LLM call) ────────────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Adjudicate one line with the deterministic engine",
        readOnlyHint=False,  # writes the evidence nodes it pinned
        destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_adjudicate_line(claim_id: str, line_number: int) -> dict[str, Any]:
    """Run the deterministic engine on one line and return the money + evidence.

    Fetches the adjudication inputs itself (line, benefit rule, accumulators, fee
    schedule, network, plan), runs ``engine.adjudicate_line`` — pure arithmetic,
    no model — and writes every input it touched to the content-addressed store,
    returning the handles as ``evidence``. The model supplies neither the inputs
    nor the amounts; it only names the line and reads the result.
    """
    AdjudicateLineIn(claim_id=claim_id, line_number=line_number)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        line = await conn.fetchrow(
            "SELECT * FROM ext.claim_lines WHERE claim_id = $1 AND line_number = $2",
            claim_id, line_number,
        )
        if line is None:
            return {"error": "line_not_found", "claim_id": claim_id, "line_number": line_number}
        claim = await conn.fetchrow("SELECT * FROM ext.claims WHERE id = $1", claim_id)
        member = await conn.fetchrow("SELECT * FROM ext.members WHERE id = $1", claim["member_id"])
        plan = await conn.fetchrow("SELECT * FROM ext.plans WHERE id = $1", member["plan_id"])
        rule = await conn.fetchrow(
            "SELECT * FROM ext.benefit_rules WHERE plan_id = $1 AND procedure_code = $2",
            plan["id"], line["procedure_code"],
        )
        allowed = await conn.fetchval(
            "SELECT allowed_cents FROM ext.fee_schedule WHERE plan_id = $1 AND procedure_code = $2",
            plan["id"], line["procedure_code"],
        )
        net = await conn.fetchrow(
            "SELECT * FROM ext.network WHERE plan_id = $1 AND provider_id = $2",
            plan["id"], claim["provider_id"],
        )
        plan_year = (line["date_of_service"] or dt.date.today()).year
        acc = await conn.fetchrow(
            "SELECT * FROM ext.accumulators WHERE member_id = $1 AND plan_year = $2",
            member["id"], plan_year,
        )

        line_d = _row(line)
        rule_d = _row(rule) if rule is not None else {"covered": False, "coverage_pct": 0}
        acc_d = _row(acc) if acc is not None else {
            "deductible_met_cents": 0, "annual_max_used_cents": 0, "oop_met_cents": 0,
        }
        plan_d = _row(plan)
        plan_d["coinsurance"] = _loads(plan_d.get("coinsurance"))
        net_d = {"in_network": bool(net["in_network"]) if net is not None else False,
                 "on_file": net is not None}

        if allowed is None:
            return {"error": "no_fee_schedule", "claim_id": claim_id, "line_number": line_number,
                    "procedure_code": line["procedure_code"]}

        result = engine_adjudicate(
            line={"procedure_code": line_d["procedure_code"], "units": line_d["units"],
                  "charged_cents": line_d["charged_cents"]},
            rule=rule_d, accumulators=acc_d, allowed_cents=int(allowed),
            network=net_d, plan=plan_d,
        )

        # Pin every input the engine used into the verifiable store; the handles
        # are the decision's evidence — content-addressed and tamper-evident.
        evidence = {
            "line": await _put_node(conn, line_d),
            "benefit_rule": await _put_node(conn, rule_d),
            "accumulators": await _put_node(conn, acc_d),
            "fee_schedule": await _put_node(conn, {"procedure_code": line_d["procedure_code"],
                                                   "allowed_cents": int(allowed)}),
            "network": await _put_node(conn, net_d),
            "plan_benefit": await _put_node(conn, {"id": plan_d["id"], "type": plan_d["type"],
                                                   "deductible_cents": plan_d["deductible_cents"],
                                                   "annual_max_cents": plan_d["annual_max_cents"],
                                                   "coinsurance": plan_d["coinsurance"]}),
        }

    out = result.as_dict()
    out.update({"claim_id": claim_id, "line_number": line_number,
                "procedure_code": line_d["procedure_code"], "evidence": evidence})
    return out


# ── 10. record_decision (writes agent.decisions proposed, with evidence) ──────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Record proposed per-line decisions with evidence",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    )
)
async def payer_record_decision(
    claim_id: str, model_version: str, prompt_version_hash: str, lines: list[dict]
) -> dict[str, Any]:
    """Persist one ``agent.decisions`` row per line (status 'proposed') + evidence.

    Idempotent per (claim_id, line_number). Computes ``requires_human`` server-side:
    any line that denies, reduces, or pends — or any claim charged above the
    auto-finalize ceiling — must be confirmed by a human reviewer.
    """
    args = RecordDecisionIn(
        claim_id=claim_id, model_version=model_version,
        prompt_version_hash=prompt_version_hash, lines=lines,
    )
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        claim = await conn.fetchrow("SELECT * FROM ext.claims WHERE id = $1", claim_id)
        if claim is None:
            return {"error": "claim_not_found", "claim_id": claim_id}

        adverse = any(ln.decision in ("deny", "reduce", "pend") for ln in args.lines)
        above_ceiling = int(claim["total_charged_cents"] or 0) > AUTO_FINALIZE_MAX_CENTS
        requires_human = adverse or above_ceiling

        recorded = []
        async with conn.transaction():
            for ln in args.lines:
                evid = await _put_node(conn, {
                    "model_version": model_version, "prompt_version_hash": prompt_version_hash,
                    "decision": ln.decision, "carc": ln.carc, "refs": ln.evidence,
                })
                full_evidence = {"refs": ln.evidence, "decision_record": evid}
                await conn.execute(
                    """
                    INSERT INTO agent.decisions
                        (claim_id, line_number, decision, allowed_cents, plan_paid_cents,
                         patient_resp_cents, deductible_cents, coinsurance_cents, copay_cents,
                         carc, rarc, rule_basis, evidence, computed_by, status, rationale)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,$13::jsonb,
                            'engine','proposed',$14)
                    ON CONFLICT (claim_id, line_number) DO UPDATE SET
                        decision = EXCLUDED.decision, allowed_cents = EXCLUDED.allowed_cents,
                        plan_paid_cents = EXCLUDED.plan_paid_cents,
                        patient_resp_cents = EXCLUDED.patient_resp_cents,
                        deductible_cents = EXCLUDED.deductible_cents,
                        coinsurance_cents = EXCLUDED.coinsurance_cents,
                        copay_cents = EXCLUDED.copay_cents, carc = EXCLUDED.carc,
                        rarc = EXCLUDED.rarc, rule_basis = EXCLUDED.rule_basis,
                        evidence = EXCLUDED.evidence, rationale = EXCLUDED.rationale,
                        status = 'proposed'
                    """,
                    claim_id, ln.line_number, ln.decision, ln.allowed_cents, ln.plan_paid_cents,
                    ln.patient_resp_cents, ln.deductible_cents, ln.coinsurance_cents, ln.copay_cents,
                    json.dumps(ln.carc), json.dumps(ln.rarc), json.dumps(ln.rule_basis),
                    json.dumps(full_evidence), ln.rationale,
                )
                recorded.append({"line_number": ln.line_number, "decision": ln.decision})

            new_status = "pended" if any(ln.decision == "pend" for ln in args.lines) else "received"
            await conn.execute("UPDATE ext.claims SET status = $1 WHERE id = $2", new_status, claim_id)

    return {
        "claim_id": claim_id, "lines_recorded": len(recorded), "decisions": recorded,
        "requires_human": requires_human,
        "reason": ("adverse_line" if adverse else ("above_ceiling" if above_ceiling else "none")),
    }


# ── 11. request_review (HITL interrupt — blocks until a human resolves) ───────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Open the human review gate (blocks until resolved)",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    )
)
async def payer_request_review(
    claim_id: str, summary: str, reason: str = "adverse_or_above_threshold",
    reviewer_role: str = "claims_examiner",
) -> dict[str, Any]:
    """Open the review gate for a claim and BLOCK until a human resolves it.

    Creates (or reuses) a pending ``agent.approvals`` row keyed by claim id, then
    polls until it leaves 'pending'. A human resolves it out of band (see
    ``scripts/reviewer_console.py``): confirm the proposed adjudication, reject,
    or modify specific lines. ``is_override`` is true when the examiner went
    against the agent — the appeal / audit evidence.
    """
    args = RequestReviewIn(claim_id=claim_id, summary=summary, reason=reason, reviewer_role=reviewer_role)
    timeout = float(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"))
    poll = float(os.environ.get("APPROVAL_POLL_SECONDS", "2"))
    pool = await db.get_pool()

    async with pool.acquire() as conn:
        proposed = await conn.fetch(
            "SELECT line_number, decision, plan_paid_cents, patient_resp_cents "
            "FROM agent.decisions WHERE claim_id = $1 ORDER BY line_number", claim_id
        )
        payload = {"summary": args.summary, "reason": args.reason,
                   "proposed": [_row(r) for r in proposed]}
        existing = await conn.fetchrow(
            "SELECT id, status FROM agent.approvals WHERE idempotency_key = $1", claim_id
        )
        if existing is not None and existing["status"] != "pending":
            return await _review_result(conn, existing["id"])
        if existing is not None:
            approval_id = existing["id"]
        else:
            approval_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO agent.approvals (id, claim_id, action, payload, idempotency_key) "
                "VALUES ($1,$2,'claim_review',$3::jsonb,$4)",
                approval_id, claim_id, json.dumps(payload), claim_id,
            )

    waited = 0.0
    while waited < timeout:
        async with pool.acquire() as conn:
            status = await conn.fetchval("SELECT status FROM agent.approvals WHERE id = $1", approval_id)
            if status and status != "pending":
                return await _review_result(conn, approval_id)
        await asyncio.sleep(poll)
        waited += poll
    return {"status": "timeout", "approval_id": str(approval_id), "waited_seconds": waited}


async def _review_result(conn: Any, approval_id: uuid.UUID) -> dict[str, Any]:
    rec = await conn.fetchrow("SELECT * FROM agent.approvals WHERE id = $1", approval_id)
    return {
        "approval_id": str(rec["id"]), "claim_id": rec["claim_id"], "status": rec["status"],
        "is_override": rec["is_override"], "decided_by": rec["decided_by"],
        "line_overrides": _loads(rec["line_overrides"]), "justification": rec["justification"],
        "decided_at": rec["decided_at"].isoformat() if rec["decided_at"] else None,
    }


# ── 12. post_adjudication (HITL commit → ext.claim_lines, the 835/EOB) ────────
@mcp.tool(
    annotations=ToolAnnotations(
        title="Commit final decisions to ext.claim_lines (the 835/EOB)",
        readOnlyHint=False, destructiveHint=False,
        idempotentHint=True,  # per (claim_id, line_number)
        openWorldHint=False,
    )
)
async def payer_post_adjudication(claim_id: str) -> dict[str, Any]:
    """Commit the final per-line decisions to ext.claim_lines (the 835/EOB result).

    Applies any reviewer line overrides, writes status / allowed / plan_paid /
    patient_resp / CARC / RARC onto each ext.claim_line, marks the agent decision
    'final', and sets the claim status. Idempotent per (claim_id, line_number),
    so a retry cannot pay twice.
    """
    PostAdjudicationIn(claim_id=claim_id)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        decisions = await conn.fetch(
            "SELECT * FROM agent.decisions WHERE claim_id = $1 ORDER BY line_number", claim_id
        )
        if not decisions:
            return {"error": "no_decisions", "claim_id": claim_id}
        appr = await conn.fetchrow(
            "SELECT * FROM agent.approvals WHERE idempotency_key = $1", claim_id
        )
        overrides = _loads(appr["line_overrides"]) if appr and appr["line_overrides"] else {}
        # Gate: if a review was required and is still pending, refuse to post.
        if appr is not None and appr["status"] == "pending":
            return {"error": "review_pending", "claim_id": claim_id,
                    "approval_id": str(appr["id"])}

        _STATUS = {"pay": "paid", "reduce": "reduced", "deny": "denied", "pend": "pended"}
        posted = []
        async with conn.transaction():
            for d in decisions:
                ov = (overrides or {}).get(str(d["line_number"])) or {}
                decision = ov.get("decision", d["decision"])
                plan_paid = ov.get("plan_paid_cents", d["plan_paid_cents"])
                patient_resp = ov.get("patient_resp_cents", d["patient_resp_cents"])
                status = _STATUS.get(decision, "pended")
                await conn.execute(
                    """UPDATE ext.claim_lines SET status=$1, allowed_cents=$2, plan_paid_cents=$3,
                       patient_resp_cents=$4, carc=$5::jsonb, rarc=$6::jsonb
                       WHERE claim_id=$7 AND line_number=$8""",
                    status, d["allowed_cents"], plan_paid, patient_resp,
                    json.dumps(_loads(d["carc"])), json.dumps(_loads(d["rarc"])),
                    claim_id, d["line_number"],
                )
                await conn.execute(
                    "UPDATE agent.decisions SET status='final', decided_at=now(), "
                    "approver=$1 WHERE claim_id=$2 AND line_number=$3",
                    (appr["decided_by"] if appr else None), claim_id, d["line_number"],
                )
                posted.append({"line_number": d["line_number"], "status": status,
                               "plan_paid_cents": plan_paid, "patient_resp_cents": patient_resp})

            statuses = {p["status"] for p in posted}
            claim_status = "pended" if "pended" in statuses else (
                "denied" if statuses == {"denied"} else "adjudicated"
            )
            await conn.execute("UPDATE ext.claims SET status=$1 WHERE id=$2", claim_status, claim_id)

    total_plan_paid = sum(p["plan_paid_cents"] or 0 for p in posted)
    total_patient = sum(p["patient_resp_cents"] or 0 for p in posted)
    return {"claim_id": claim_id, "claim_status": claim_status, "lines_posted": len(posted),
            "lines": posted, "total_plan_paid_cents": total_plan_paid,
            "total_patient_resp_cents": total_patient}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
