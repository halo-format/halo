"""Run the SAME agent against the RAW Claude Messages API (no Agent SDK, no CLI).

This is the second runtime for the example: a manual agentic loop on
``anthropic.Anthropic().messages.create(...)`` with the 13 ``mimic-payer`` tools
declared as raw tool definitions and executed in-process by calling the existing
server functions. The deterministic engine, the DB, the human-review gate, the
evidence store, and the reason-code reference are all reused unchanged — only the
runtime around them differs. That is the whole point of the architecture: the
tools are the swap point, everything above them is portable.

    HALO=0 RUN_LABEL=raw_baseline python -m scripts.run_raw_api CLM-PROF
    HALO=1 RUN_LABEL=raw_halo     python -m scripts.run_raw_api CLM-PROF

With ``HALO=1`` the Agent-SDK PostToolUse hook is replaced by an explicit encode
step in this loop: a large tool result is encoded into a Halo store and the model
receives the shape map instead of the payload, plus a ``halo_fetch`` tool to pull
the fields it needs (verified on read). That mechanism is the published adapter's
raw-Messages-API surface (``halo_format_claude.raw.create_raw_halo``) — the same
engine the Agent SDK path drives via a hook — so this script carries no Halo code
of its own; the raw Messages API has no hook, so the loop drives it by hand.

Requires ANTHROPIC_API_KEY and a seeded mimic_payer database. For a claim that
hits the human-review gate, run ``python -m scripts.reviewer_console auto`` in a
second terminal (CLM-PROF auto-finalizes, so it needs no examiner).

Use ``--selftest`` to exercise the tool dispatch + Halo encode/fetch plumbing
WITHOUT calling the API (no key needed).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from agent.prompts import MODEL_VERSION, SYSTEM_PROMPT
from mcp_servers.mimic_payer import server as S

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

HALO_ENABLED = os.environ.get("HALO", "").lower() in ("1", "true", "yes", "on")
HALO_THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))
MAX_TURNS = int(os.environ.get("RAW_MAX_TURNS", "40"))

# Per-1M-token rates ($) for a quick cost estimate; cache_write is the 5-min TTL rate.
PRICING = {
    "claude-opus-4-8":   {"in": 5.0, "out": 25.0, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":  {"in": 1.0, "out": 5.0,  "cache_read": 0.10, "cache_write": 1.25},
}

# ── the 13 mimic-payer tools as raw Messages API tool definitions ─────────────
def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}

_STR = {"type": "string"}
_INT = {"type": "integer"}
_STRARR = {"type": "array", "items": {"type": "string"}}

TOOL_DEFS = [
    ("payer_get_agent_provenance", "Return the canonical prompt_version_hash (sha256 over CLAUDE.md).", _obj({}, [])),
    ("payer_get_claim", "Fetch the 837 claim: header + lines + diagnosis + attachment MANIFEST (refs + metadata, not bodies).", _obj({"claim_id": _STR}, ["claim_id"])),
    ("payer_get_attachment", "Fetch ONE attachment body for documentation review (large: narrative + findings + tooth_chart + raw image_b64). Read narrative/findings; never read image_b64.", _obj({"claim_id": _STR, "attachment_ref": _STR}, ["claim_id", "attachment_ref"])),
    ("payer_get_attachments", "Batch: fetch several attachment bodies for a claim in one call.", _obj({"claim_id": _STR, "attachment_refs": _STRARR}, ["claim_id", "attachment_refs"])),
    ("payer_get_member_coverage", "Member eligibility, effective dates, and the plan benefit design.", _obj({"member_id": _STR}, ["member_id"])),
    ("payer_get_benefit_rules", "Per-code coverage %, frequency, waiting, preauth, category. Pass procedure_codes for this claim's codes only.", _obj({"plan_id": _STR, "procedure_codes": _STRARR}, ["plan_id"])),
    ("payer_get_accumulators", "Deductible met, annual max used, OOP met for the plan year.", _obj({"member_id": _STR, "plan_year": _INT}, ["member_id", "plan_year"])),
    ("payer_get_claim_history", "Prior adjudicated lines for frequency/duplicate checks (heavy). Slice with procedure_code.", _obj({"member_id": _STR, "procedure_code": _STR, "window_days": _INT}, ["member_id"])),
    ("payer_check_network", "In / out of network for (provider, plan).", _obj({"provider_id": _STR, "plan_id": _STR}, ["provider_id", "plan_id"])),
    ("payer_get_allowed_amount", "Fee-schedule allowed amounts for the codes on the claim.", _obj({"plan_id": _STR, "procedure_codes": _STRARR}, ["plan_id", "procedure_codes"])),
    ("payer_lookup_reason_code", "CARC / RARC description. Select from these; never invent a code.", _obj({"code": _STR}, ["code"])),
    ("payer_adjudicate_line", "Run the DETERMINISTIC engine on one line; returns the money + evidence handles.", _obj({"claim_id": _STR, "line_number": _INT}, ["claim_id", "line_number"])),
    ("payer_record_decision", "Persist proposed per-line decisions with evidence. lines is a list of per-line decision objects.", _obj({"claim_id": _STR, "model_version": _STR, "prompt_version_hash": _STR, "lines": {"type": "array", "items": {"type": "object"}}}, ["claim_id", "model_version", "prompt_version_hash", "lines"])),
    ("payer_request_review", "Open the human review gate; BLOCKS until a claims examiner resolves it.", _obj({"claim_id": _STR, "summary": _STR, "reason": _STR, "reviewer_role": _STR}, ["claim_id", "summary"])),
    ("payer_post_adjudication", "Commit final decisions to ext.claim_lines (the 835/EOB). Idempotent per line.", _obj({"claim_id": _STR}, ["claim_id"])),
]

DISPATCH = {name: getattr(S, name) for name, _, _ in TOOL_DEFS}

# A one-line domain hint appended to the package's generic navigation guidance.
DOMAIN_HINT = (
    "\nFor a claim, fetch the service `lines` from the map. For a line needing documentation review "
    "(major restorative, endodontic, periodontal, oral surgery), call payer_get_attachment for its "
    "supporting attachment and read ONLY `narrative` and `findings` — never fetch `image_b64` (raw "
    "pixels: large and unreadable). Routine preventive/basic lines need no attachment."
)


def build_tools(halo_tool_def: dict | None) -> list[dict]:
    defs = [{"name": n, "description": d, "input_schema": s} for n, d, s in TOOL_DEFS]
    if halo_tool_def is not None:
        defs.append(halo_tool_def)
    defs[-1]["cache_control"] = {"type": "ephemeral"}  # cache tools + system together
    return defs


async def _execute(name: str, args: dict, adapter) -> str:
    """Run one tool and return the tool_result text (Halo-encoded if large and halo is on)."""
    if adapter is not None and adapter.is_fetch(name):
        # MANDATORY: never re-encode a fetched leaf, or the model never sees the value.
        return adapter.fetch(args["refs"])
    result = await DISPATCH[name](**args)
    if adapter is not None:
        return adapter.encode_result(name, args, result)
    return json.dumps(result)


def _cost(usage: dict, model: str) -> float | None:
    p = PRICING.get(model)
    if p is None:
        return None
    m = 1_000_000
    return round(
        usage.get("input_tokens", 0) * p["in"] / m
        + usage.get("output_tokens", 0) * p["out"] / m
        + usage.get("cache_read_input_tokens", 0) * p["cache_read"] / m
        + usage.get("cache_creation_input_tokens", 0) * p["cache_write"] / m,
        6,
    )


async def run(claim_id: str) -> None:
    import anthropic

    halo = HALO_ENABLED
    label = os.environ.get("RUN_LABEL", "raw_halo" if halo else "raw_baseline")
    client = anthropic.AsyncAnthropic()
    adapter = None
    if halo:
        from halo_format_claude.raw import create_raw_halo

        adapter = create_raw_halo(threshold=HALO_THRESHOLD)

    guidance = (adapter.guidance + DOMAIN_HINT) if adapter else ""
    system = [{"type": "text", "text": SYSTEM_PROMPT + guidance,
               "cache_control": {"type": "ephemeral"}}]
    tools = build_tools(adapter.tool_def if adapter else None)
    prompt = (
        f"Adjudicate insurance claim {claim_id} end to end: decide each service line "
        f"(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, "
        f"record the decisions with evidence, open the review gate and wait for the examiner if "
        f"required, then post the adjudication. Finish with a one-line per-line summary."
    )
    messages: list[dict] = [{"role": "user", "content": prompt}]

    usage = Counter()
    tool_calls: Counter = Counter()
    turns = 0

    print(f"=== Insurance Claim Decision Agent — RAW Claude API — {claim_id} — "
          f"{'HALO' if halo else 'BASELINE'} (model {MODEL_VERSION}) ===\n")

    while turns < MAX_TURNS:
        turns += 1
        resp = await client.messages.create(
            model=MODEL_VERSION, max_tokens=8000, system=system, tools=tools, messages=messages,
        )
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            usage[k] += getattr(resp.usage, k, 0) or 0

        for block in resp.content:
            if block.type == "text" and block.text.strip():
                print(block.text, flush=True)
            elif block.type == "tool_use":
                tool_calls[block.name] += 1
                print(f"  → {block.name} {json.dumps(block.input)[:120]}", flush=True)

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if block.type == "tool_use":
                try:
                    text = await _execute(block.name, dict(block.input), adapter)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
                except Exception as e:  # surface tool errors back to the model
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"error: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})

    summary = {
        "label": label, "runtime": "raw_messages_api", "halo_enabled": halo, "model": MODEL_VERSION,
        "tokens": dict(usage), "total_tokens": sum(usage.values()),
        "estimated_cost_usd": _cost(usage, MODEL_VERSION),
        "turns": turns, "tool_calls": dict(tool_calls),
        "halo_fetch_calls": tool_calls.get("halo_fetch", 0),
        "halo_maps": len(getattr(adapter.session, "_maps", {})) if adapter else 0,
    }
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{label}.json").write_text(json.dumps(summary, indent=2))
    print(f"\n=== {label} === tokens={summary['total_tokens']:,} cost=${summary['estimated_cost_usd']} "
          f"turns={turns} tool_calls={sum(tool_calls.values())} halo_fetch={summary['halo_fetch_calls']}")
    print(f"(written to runs/{label}.json)")


async def selftest(claim_id: str) -> None:
    """Exercise tool dispatch + Halo encode/fetch with NO API call (no key needed)."""
    from halo_format_claude.raw import create_raw_halo

    print("== raw-api self-test (no API call) ==")
    prov = await S.payer_get_agent_provenance()
    print("provenance tool ok:", prov["agent_id"])

    adapter = create_raw_halo(threshold=HALO_THRESHOLD)
    claim = await S.payer_get_claim(claim_id)
    full = json.dumps(claim)
    shape = adapter.encode_result("payer_get_claim", {"claim_id": claim_id}, claim)
    print(f"get_claim: full={len(full)}B  shape_map_model_sees={len(shape)}B  "
          f"({100*(1-len(shape)/len(full)):.0f}% smaller)")
    ref = f"{claim_id}.lines"
    fetched = json.loads(adapter.fetch([ref]))
    ok = fetched[ref]["ok"] and isinstance(fetched[ref]["value"], list)
    print(f"halo_fetch(['{ref}']) verified ok: {ok} ({len(fetched[ref]['value'])} lines)")
    eng = await S.payer_adjudicate_line(claim_id, 1)
    print(f"engine adjudicate_line(1): plan_paid={eng['plan_paid_cents']} "
          f"review_required={eng['review_required']}")
    print(f"tools wired: {len(TOOL_DEFS)} domain tools + halo_fetch")
    print("== self-test OK: tool dispatch + Halo encode/fetch all functional ==")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cid = args[0] if args else "CLM-PROF"
    if "--selftest" in sys.argv:
        asyncio.run(selftest(cid))
    else:
        asyncio.run(run(cid))
