"""The 15 payer tools as LangChain tools, for the LangGraph agent.

Each tool wraps the same SQL on ext.*/agent.* and the same deterministic engine as
every other port of this agent — only the framing changes (LangChain ``@tool``).
The contract is the swap point: SQL today, real payer feeds later.

The claim API is normalized REST-style (matching the other ports): ``payer_get_claim``
returns the header, lines, diagnosis, and an attachment **manifest** — references and
light metadata (kind, byte size, which line each documents), NOT the bodies. The bulky
clinical bodies (narrative, findings, tooth chart, and a large raw ``image_b64`` blob)
are fetched on demand with ``payer_get_attachment`` / ``payer_get_attachments`` only for
a line that needs clinical documentation review. So a real heavy payload exists, but it
crosses the wire only when actually used.

NOTE: this example deliberately ships **without** a Halo integration — tools return
plain JSON. The Halo host adapter for LangGraph (which keeps large tool results out of
the model's context and records content-addressed evidence) is wired in separately; the
on-demand attachment body — narrative/findings the reviewer reads, plus an ``image_b64``
blob it never reads — is exactly the payload that adapter encodes.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import json
import os
import random
import uuid
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import tool

from . import db
from .engine import adjudicate_line

AUTO_FINALIZE_MAX_CENTS = int(os.environ.get("AUTO_FINALIZE_MAX_CENTS", "50000"))
_CLAUDE_MD = Path(__file__).resolve().parent.parent / "CLAUDE.md"


# ── helpers ───────────────────────────────────────────────────────────────────
def _jsonify(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonify(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonify(x) for x in v]
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def _row(r: Any) -> Optional[dict]:
    return _jsonify(dict(r)) if r is not None else None


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _prompt_hash() -> str:
    try:
        return "sha256:" + hashlib.sha256(_CLAUDE_MD.read_bytes()).hexdigest()
    except OSError:
        return "sha256:unknown"


# ── attachment synthesis (deterministic from claim_id + ref) ─────────────────
# A claim references attachments; the bodies are retrieved separately. The body carries
# a large raw image blob (image_b64) a reviewer never reads — only the narrative/findings
# matter — which is exactly the field Halo lets the model skip. Synthesis matches the
# other ports so the same claim yields the same attachment content.
_ATTACH_KINDS = ["periapical_xray", "bitewing_xray", "panoramic_xray", "perio_chart", "clinical_note"]
_NARRATIVE = (
    "Patient presents for evaluation. Intraoral examination performed; findings documented "
    "per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment "
    "plan discussed with the patient and informed consent obtained. No adverse reaction noted."
)
_FINDINGS = [
    "Radiograph supports the proposed restoration; margins intact, no periapical pathology.",
    "Generalized moderate periodontitis; scaling and root planing indicated for the quadrant.",
    "Deep carious lesion approximating the pulp; crown indicated to restore the tooth.",
    "No acute findings; documentation supports the submitted procedure.",
]


def _needs_documentation(procedure_code: str) -> bool:
    """Major restorative / endodontic / periodontal / oral-surgery codes need a clinical
    attachment. Preventive (D01/D11) and basic single-surface restorations do not."""
    code = (procedure_code or "").upper()
    return (
        code.startswith(("D27", "D6"))                  # crowns / fixed prosthodontics
        or code.startswith("D3")                        # endodontics
        or (code.startswith("D4") and code >= "D4210")  # periodontal surgery / scaling
        or code.startswith("D7")                        # oral surgery
    )


def _attachment_fields(claim_id: str, ref: str) -> tuple[str, str, int, int, str]:
    """Deterministic scalar fields for one attachment, drawn in a FIXED order so the
    manifest (get_claim) and the body (get_attachment) always agree."""
    rng = random.Random(int(hashlib.sha256(f"{claim_id}/{ref}".encode()).hexdigest()[:12], 16))
    kind = rng.choice(_ATTACH_KINDS)
    captured_at = f"2026-0{rng.randint(1, 5)}-{rng.randint(10, 28)}"
    image_kb = rng.randint(18, 40)          # the bulky raw-image payload, in KB
    narrative_repeat = rng.randint(2, 4)
    finding = rng.choice(_FINDINGS)
    return kind, captured_at, image_kb, narrative_repeat, finding


def _attachment_manifest(claim_id: str, lines: list[dict], refs: list[str] | None) -> list[dict]:
    """Light per-attachment metadata: ref, kind, capture date, byte size, and which line it
    documents. No bodies — this is what a claim fetch should return."""
    refs = refs or []
    doc_lines = [ln["line_number"] for ln in (lines or []) if _needs_documentation(ln.get("procedure_code", ""))]
    manifest = []
    for i, ref in enumerate(refs):
        kind, captured_at, image_kb, _, _ = _attachment_fields(claim_id, ref)
        manifest.append({
            "ref": ref, "kind": kind, "captured_at": captured_at, "modality": "intraoral",
            "image_bytes": image_kb * 1024,
            "documents_line": doc_lines[i] if i < len(doc_lines) else None,
        })
    return manifest


def _attachment_body(claim_id: str, ref: str) -> dict:
    """The full attachment: clinical narrative + findings + tooth chart + a large raw image
    blob. ``image_b64`` is the bulk — a reviewer reads narrative/findings, never the pixels —
    so under Halo the model fetches those small fields and skips the blob."""
    kind, captured_at, image_kb, narrative_repeat, finding = _attachment_fields(claim_id, ref)
    chart_rng = random.Random(int(hashlib.sha256(f"{claim_id}/{ref}/chart".encode()).hexdigest()[:12], 16))
    blob = hashlib.sha256(f"{claim_id}/{ref}/image".encode()).digest()
    image_b64 = base64.b64encode(blob * max(1, image_kb * 1024 // len(blob))).decode()
    return {
        "attachment_ref": ref, "claim_id": claim_id, "kind": kind, "captured_at": captured_at,
        "narrative": " ".join([_NARRATIVE] * narrative_repeat),
        "findings": finding,
        "tooth_chart": {str(t): chart_rng.choice(["sound", "restored", "caries", "missing"]) for t in range(1, 33)},
        "image_meta": {"dpi": 300, "bytes": image_kb * 1024, "modality": "intraoral"},
        "image_b64": image_b64,   # raw pixels — large, not human-readable; do not fetch for review
    }


# ── tools ─────────────────────────────────────────────────────────────────────
@tool
async def payer_get_agent_provenance() -> str:
    """Return the canonical prompt_version_hash (sha256 over CLAUDE.md). Call before recording."""
    return json.dumps({"prompt_version_hash": _prompt_hash(), "prompt_source": "CLAUDE.md",
                       "agent_id": "insurance-claim-decision-agent"})


@tool
async def payer_get_claim(claim_id: str) -> str:
    """Fetch the 837 claim: header, service lines, diagnosis, and an attachment MANIFEST.

    Normalized like a real payer/X12 API: this returns attachment *references* and light
    metadata (kind, byte size, which line each documents) — NOT the bodies. The bulky
    clinical bodies are fetched on demand with ``payer_get_attachment`` only when a line
    needs documentation review, so the body bytes never enter context unless actually used.
    """
    pool = await db.get_pool()
    async with pool.acquire() as c:
        claim = await c.fetchrow("SELECT * FROM ext.claims WHERE id=$1", claim_id)
        if claim is None:
            return json.dumps({"error": "claim_not_found", "claim_id": claim_id})
        lines = await c.fetch("SELECT * FROM ext.claim_lines WHERE claim_id=$1 ORDER BY line_number", claim_id)
    out = _row(claim)
    out["diagnosis_codes"] = _loads(out.get("diagnosis_codes"))
    out["lines"] = [_row(r) for r in lines]
    out["attachments"] = _attachment_manifest(out["id"], out["lines"], _loads(out.get("attachments")))
    return json.dumps(out)


@tool
async def payer_get_attachment(claim_id: str, attachment_ref: str) -> str:
    """Fetch ONE attachment's full body for clinical documentation review.

    Large by nature — it carries the raw image (``image_b64``) plus the narrative, findings,
    and tooth chart. For review you only need ``narrative`` / ``findings``; the raw image is
    bulk you never read. Fetch this only for a line that needs documentation (major
    restorative, endodontic, periodontal, oral surgery).
    """
    pool = await db.get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT attachments FROM ext.claims WHERE id=$1", claim_id)
    if row is None:
        return json.dumps({"error": "claim_not_found", "claim_id": claim_id})
    if attachment_ref not in (_loads(row["attachments"]) or []):
        return json.dumps({"error": "attachment_not_found", "claim_id": claim_id, "attachment_ref": attachment_ref})
    return json.dumps(_attachment_body(claim_id, attachment_ref))


@tool
async def payer_get_attachments(claim_id: str, attachment_refs: list[str]) -> str:
    """Batch form of payer_get_attachment — fetch several attachment bodies in one call."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow("SELECT attachments FROM ext.claims WHERE id=$1", claim_id)
    if row is None:
        return json.dumps({"error": "claim_not_found", "claim_id": claim_id})
    valid = set(_loads(row["attachments"]) or [])
    return json.dumps({"claim_id": claim_id,
                       "attachments": [_attachment_body(claim_id, r) for r in attachment_refs if r in valid]})


@tool
async def payer_get_member_coverage(member_id: str) -> str:
    """Member eligibility, effective dates, and the plan benefit design."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        m = await c.fetchrow("SELECT * FROM ext.members WHERE id=$1", member_id)
        if m is None:
            return json.dumps({"error": "member_not_found", "member_id": member_id})
        p = await c.fetchrow("SELECT * FROM ext.plans WHERE id=$1", m["plan_id"])
    pd = _row(p)
    if pd:
        pd["coinsurance"] = _loads(pd.get("coinsurance"))
    return json.dumps({"member": _row(m), "plan": pd})


@tool
async def payer_get_benefit_rules(plan_id: str, procedure_codes: Optional[list[str]] = None) -> str:
    """Per-code coverage %, frequency, waiting, preauth, category. Pass this claim's codes only."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        if procedure_codes:
            rows = await c.fetch("SELECT * FROM ext.benefit_rules WHERE plan_id=$1 AND procedure_code=ANY($2::text[])", plan_id, procedure_codes)
        else:
            rows = await c.fetch("SELECT * FROM ext.benefit_rules WHERE plan_id=$1", plan_id)
    return json.dumps({"plan_id": plan_id, "rules": [_row(r) for r in rows]})


@tool
async def payer_get_accumulators(member_id: str, plan_year: int) -> str:
    """Deductible met, annual max used, OOP met for the plan year."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        r = await c.fetchrow("SELECT * FROM ext.accumulators WHERE member_id=$1 AND plan_year=$2", member_id, plan_year)
    return json.dumps(_row(r) or {"member_id": member_id, "plan_year": plan_year,
                                  "deductible_met_cents": 0, "annual_max_used_cents": 0, "oop_met_cents": 0})


@tool
async def payer_get_claim_history(member_id: str, procedure_code: Optional[str] = None, window_days: int = 365) -> str:
    """Prior adjudicated lines for frequency/duplicate checks (heavy). Slice with procedure_code."""
    since = dt.date.today() - dt.timedelta(days=window_days)
    pool = await db.get_pool()
    async with pool.acquire() as c:
        if procedure_code:
            rows = await c.fetch("""SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id=cl.claim_id
                WHERE c.member_id=$1 AND cl.procedure_code=$2 AND cl.date_of_service>=$3 ORDER BY cl.date_of_service DESC""", member_id, procedure_code, since)
        else:
            rows = await c.fetch("""SELECT cl.* FROM ext.claim_lines cl JOIN ext.claims c ON c.id=cl.claim_id
                WHERE c.member_id=$1 AND cl.date_of_service>=$2 AND c.status<>'received' ORDER BY cl.date_of_service DESC""", member_id, since)
    hist = [_row(r) for r in rows]
    for h in hist:
        h["carc"] = _loads(h.get("carc")); h["rarc"] = _loads(h.get("rarc"))
    return json.dumps({"member_id": member_id, "procedure_code": procedure_code, "lines": hist})


@tool
async def payer_check_network(provider_id: str, plan_id: str) -> str:
    """In / out of network for (provider, plan)."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        r = await c.fetchrow("SELECT * FROM ext.network WHERE plan_id=$1 AND provider_id=$2", plan_id, provider_id)
    if r is None:
        return json.dumps({"plan_id": plan_id, "provider_id": provider_id, "in_network": False, "on_file": False})
    out = _row(r); out["on_file"] = True
    return json.dumps(out)


@tool
async def payer_get_allowed_amount(plan_id: str, procedure_codes: list[str]) -> str:
    """Fee-schedule allowed amounts for the codes on the claim."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch("SELECT procedure_code, allowed_cents FROM ext.fee_schedule WHERE plan_id=$1 AND procedure_code=ANY($2::text[])", plan_id, procedure_codes)
    return json.dumps({"plan_id": plan_id, "allowed": {r["procedure_code"]: r["allowed_cents"] for r in rows}})


@tool
async def payer_lookup_reason_code(code: str) -> str:
    """CARC / RARC description. Select from these; never invent a code."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        r = await c.fetchrow("SELECT * FROM ext.reason_codes WHERE code=$1", code)
    return json.dumps(_row(r) or {"error": "unknown_reason_code", "code": code})


@tool
async def payer_adjudicate_line(claim_id: str, line_number: int) -> str:
    """Run the DETERMINISTIC engine on one line. Fetches its own inputs; returns the money +
    suggested CARC/RARC + review flags. The model never supplies or computes an amount."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        line = await c.fetchrow("SELECT * FROM ext.claim_lines WHERE claim_id=$1 AND line_number=$2", claim_id, line_number)
        if line is None:
            return json.dumps({"error": "line_not_found", "claim_id": claim_id, "line_number": line_number})
        claim = await c.fetchrow("SELECT * FROM ext.claims WHERE id=$1", claim_id)
        member = await c.fetchrow("SELECT * FROM ext.members WHERE id=$1", claim["member_id"])
        plan = await c.fetchrow("SELECT * FROM ext.plans WHERE id=$1", member["plan_id"])
        rule = await c.fetchrow("SELECT * FROM ext.benefit_rules WHERE plan_id=$1 AND procedure_code=$2", plan["id"], line["procedure_code"])
        allowed = await c.fetchval("SELECT allowed_cents FROM ext.fee_schedule WHERE plan_id=$1 AND procedure_code=$2", plan["id"], line["procedure_code"])
        net = await c.fetchrow("SELECT * FROM ext.network WHERE plan_id=$1 AND provider_id=$2", plan["id"], claim["provider_id"])
        py = (line["date_of_service"] or dt.date.today()).year
        acc = await c.fetchrow("SELECT * FROM ext.accumulators WHERE member_id=$1 AND plan_year=$2", member["id"], py)
    if allowed is None:
        return json.dumps({"error": "no_fee_schedule", "claim_id": claim_id, "line_number": line_number})

    line_d = _row(line)
    rule_d = _row(rule) if rule is not None else {"covered": False, "coverage_pct": 0}
    acc_d = _row(acc) if acc is not None else {"deductible_met_cents": 0, "annual_max_used_cents": 0, "oop_met_cents": 0}
    plan_d = _row(plan); plan_d["coinsurance"] = _loads(plan_d.get("coinsurance"))
    net_d = {"in_network": bool(net["in_network"]) if net is not None else False, "on_file": net is not None}

    result = adjudicate_line(
        line={"procedure_code": line_d["procedure_code"], "units": line_d["units"], "charged_cents": line_d["charged_cents"]},
        rule=rule_d, accumulators=acc_d, allowed_cents=int(allowed), network=net_d, plan=plan_d,
    )
    out = result.as_dict()
    out.update({"claim_id": claim_id, "line_number": line_number, "procedure_code": line_d["procedure_code"]})
    return json.dumps(out)


@tool
async def payer_record_decision(claim_id: str, model_version: str, prompt_version_hash: str, lines: list[dict]) -> str:
    """Persist proposed per-line decisions (status 'proposed'). lines is a list of per-line decision
    objects. Computes requires_human server-side: any deny/reduce/pend, or a claim above the ceiling."""
    pool = await db.get_pool()
    async with pool.acquire() as c:
        claim = await c.fetchrow("SELECT * FROM ext.claims WHERE id=$1", claim_id)
        if claim is None:
            return json.dumps({"error": "claim_not_found", "claim_id": claim_id})
        adverse = any(l.get("decision") in ("deny", "reduce", "pend") for l in lines)
        above = int(claim["total_charged_cents"] or 0) > AUTO_FINALIZE_MAX_CENTS
        requires_human = adverse or above
        async with c.transaction():
            for l in lines:
                await c.execute("""INSERT INTO agent.decisions
                    (claim_id, line_number, decision, allowed_cents, plan_paid_cents, patient_resp_cents,
                     deductible_cents, coinsurance_cents, copay_cents, carc, rarc, rule_basis, computed_by, status, rationale)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12::jsonb,'engine','proposed',$13)
                    ON CONFLICT (claim_id, line_number) DO UPDATE SET decision=EXCLUDED.decision,
                     allowed_cents=EXCLUDED.allowed_cents, plan_paid_cents=EXCLUDED.plan_paid_cents,
                     patient_resp_cents=EXCLUDED.patient_resp_cents, deductible_cents=EXCLUDED.deductible_cents,
                     coinsurance_cents=EXCLUDED.coinsurance_cents, copay_cents=EXCLUDED.copay_cents,
                     carc=EXCLUDED.carc, rarc=EXCLUDED.rarc, rule_basis=EXCLUDED.rule_basis,
                     rationale=EXCLUDED.rationale, status='proposed'""",
                    claim_id, l["line_number"], l["decision"], l.get("allowed_cents", 0), l.get("plan_paid_cents", 0),
                    l.get("patient_resp_cents", 0), l.get("deductible_cents", 0), l.get("coinsurance_cents", 0), l.get("copay_cents", 0),
                    json.dumps(l.get("carc", [])), json.dumps(l.get("rarc", [])), json.dumps(l.get("rule_basis", [])), l.get("rationale", ""))
            new_status = "pended" if any(l.get("decision") == "pend" for l in lines) else "received"
            await c.execute("UPDATE ext.claims SET status=$1 WHERE id=$2", new_status, claim_id)
    return json.dumps({"claim_id": claim_id, "lines_recorded": len(lines), "requires_human": requires_human,
                       "reason": "adverse_line" if adverse else "above_ceiling" if above else "none"})


@tool
async def payer_request_review(claim_id: str, summary: str, reason: str = "adverse_or_above_threshold") -> str:
    """Open the human review gate; BLOCKS until a claims examiner resolves it."""
    timeout = float(os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"))
    poll = float(os.environ.get("APPROVAL_POLL_SECONDS", "2"))
    pool = await db.get_pool()
    async with pool.acquire() as c:
        proposed = await c.fetch("SELECT line_number, decision, plan_paid_cents, patient_resp_cents FROM agent.decisions WHERE claim_id=$1 ORDER BY line_number", claim_id)
        payload = json.dumps({"summary": summary, "reason": reason, "proposed": [_row(r) for r in proposed]})
        existing = await c.fetchrow("SELECT id, status FROM agent.approvals WHERE idempotency_key=$1", claim_id)
        if existing is not None and existing["status"] != "pending":
            return await _review_result(c, existing["id"])
        approval_id = existing["id"] if existing else uuid.uuid4()
        if not existing:
            await c.execute("INSERT INTO agent.approvals (id, claim_id, action, payload, idempotency_key) VALUES ($1,$2,'claim_review',$3::jsonb,$4)", approval_id, claim_id, payload, claim_id)
    waited = 0.0
    while waited < timeout:
        async with pool.acquire() as c:
            status = await c.fetchval("SELECT status FROM agent.approvals WHERE id=$1", approval_id)
            if status and status != "pending":
                return await _review_result(c, approval_id)
        await asyncio.sleep(poll); waited += poll
    return json.dumps({"status": "timeout", "approval_id": str(approval_id)})


async def _review_result(c: Any, approval_id: Any) -> str:
    r = await c.fetchrow("SELECT * FROM agent.approvals WHERE id=$1", approval_id)
    return json.dumps({"approval_id": str(r["id"]), "claim_id": r["claim_id"], "status": r["status"],
                       "is_override": r["is_override"], "decided_by": r["decided_by"],
                       "line_overrides": _loads(r["line_overrides"]), "justification": r["justification"]})


@tool
async def payer_post_adjudication(claim_id: str) -> str:
    """Commit final decisions to ext.claim_lines (the 835/EOB). Idempotent per (claim_id, line_number)."""
    _STATUS = {"pay": "paid", "reduce": "reduced", "deny": "denied", "pend": "pended"}
    pool = await db.get_pool()
    async with pool.acquire() as c:
        decisions = await c.fetch("SELECT * FROM agent.decisions WHERE claim_id=$1 ORDER BY line_number", claim_id)
        if not decisions:
            return json.dumps({"error": "no_decisions", "claim_id": claim_id})
        appr = await c.fetchrow("SELECT * FROM agent.approvals WHERE idempotency_key=$1", claim_id)
        if appr is not None and appr["status"] == "pending":
            return json.dumps({"error": "review_pending", "claim_id": claim_id})
        overrides = _loads(appr["line_overrides"]) if appr and appr["line_overrides"] else {}
        posted = []
        async with c.transaction():
            for d in decisions:
                ov = (overrides or {}).get(str(d["line_number"])) or {}
                decision = ov.get("decision", d["decision"])
                plan_paid = ov.get("plan_paid_cents", d["plan_paid_cents"])
                patient = ov.get("patient_resp_cents", d["patient_resp_cents"])
                status = _STATUS.get(decision, "pended")
                await c.execute("UPDATE ext.claim_lines SET status=$1, allowed_cents=$2, plan_paid_cents=$3, patient_resp_cents=$4, carc=$5::jsonb, rarc=$6::jsonb WHERE claim_id=$7 AND line_number=$8",
                    status, d["allowed_cents"], plan_paid, patient, json.dumps(_loads(d["carc"])), json.dumps(_loads(d["rarc"])), claim_id, d["line_number"])
                await c.execute("UPDATE agent.decisions SET status='final', decided_at=now(), approver=$1 WHERE claim_id=$2 AND line_number=$3", appr["decided_by"] if appr else None, claim_id, d["line_number"])
                posted.append({"line_number": d["line_number"], "status": status, "plan_paid_cents": plan_paid, "patient_resp_cents": patient})
            statuses = {p["status"] for p in posted}
            cs = "pended" if "pended" in statuses else "denied" if statuses == {"denied"} else "adjudicated"
            await c.execute("UPDATE ext.claims SET status=$1 WHERE id=$2", cs, claim_id)
    return json.dumps({"claim_id": claim_id, "claim_status": cs, "lines": posted,
                       "total_plan_paid_cents": sum(p["plan_paid_cents"] or 0 for p in posted),
                       "total_patient_resp_cents": sum(p["patient_resp_cents"] or 0 for p in posted)})


TOOLS = [
    payer_get_agent_provenance, payer_get_claim, payer_get_attachment, payer_get_attachments,
    payer_get_member_coverage, payer_get_benefit_rules, payer_get_accumulators, payer_get_claim_history,
    payer_check_network, payer_get_allowed_amount, payer_lookup_reason_code, payer_adjudicate_line,
    payer_record_decision, payer_request_review, payer_post_adjudication,
]
