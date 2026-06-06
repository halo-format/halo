"""Run the insurance-claim agent on LangGraph, with Claude.

A prebuilt tool-calling agent (LangChain v1 / LangGraph): `create_agent` drives the
model-calls-tools loop over the 13 payer tools, with `ChatAnthropic` as the model.
The deterministic engine, the human-review gate, and the reason codes are reused
unchanged — only the harness is LangGraph.

    python -m agent.main CLM-PROF          # adjudicate a claim end to end
    python -m agent.main CLM-PROF --selftest   # tool dispatch + engine, no API key

This example ships WITHOUT a Halo integration — tools return plain JSON. The Halo
host adapter for LangGraph attaches separately (it keeps large tool results out of
the model's context and records content-addressed evidence); this is the clean
agent it wraps.

Requires ANTHROPIC_API_KEY and a seeded mimic_payer database. For a claim with
adverse lines (CLM-1001), run scripts/reviewer_console.py in a second terminal.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from .prompts import MODEL_VERSION, SYSTEM_PROMPT
from .tools import TOOLS

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
MAX_STEPS = int(os.environ.get("LG_RECURSION_LIMIT", "120"))

PRICING = {
    "claude-opus-4-8": {"in": 5.0, "out": 25.0, "cr": 0.5, "cw": 6.25},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "cr": 0.3, "cw": 3.75},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0, "cr": 0.1, "cw": 1.25},
}


def _cost(u: dict, model: str):
    p = PRICING.get(model)
    if not p:
        return None
    m = 1_000_000
    return round(u.get("input_tokens", 0) * p["in"] / m + u.get("output_tokens", 0) * p["out"] / m
                 + u.get("cache_read", 0) * p["cr"] / m + u.get("cache_creation", 0) * p["cw"] / m, 6)


# ── Halo toggle ───────────────────────────────────────────────────────────────
# HALO=1 attaches the Halo LangGraph adapter: a wrap_tool_call middleware encodes any
# large tool result (the on-demand attachment body) into a content-addressed store and
# hands the model a shape map, plus a halo_fetch tool to pull back only the fields it
# needs. Guidance rides in the system prompt (prompt mode) — no skills system needed.
HALO_ENABLED = os.environ.get("HALO", "").lower() in ("1", "true", "yes", "on")
HALO_THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))
# CACHE=1 turns on Anthropic prompt caching (ChatAnthropic does not by default). Applies to both the
# baseline and Halo arms, so the A/B stays fair — see agent/caching.py.
CACHE_ENABLED = os.environ.get("CACHE", "").lower() in ("1", "true", "yes", "on")

HALO_GUIDANCE = """

## Large tool results (Halo)

Some tool results come back not as the full payload but as a Halo **shape map** — a
`[halo] map …` note with a root kind and one line per field (ref, kind, and a bounded
preview). The full data is held, verified, out of your context.

- Read the shape map first; the previews are sized to let you decide, so most steps need
  no fetch at all.
- To read a field you still need, call `halo_fetch(refs=[...])` with an ARRAY of refs —
  batch every ref a step needs into ONE call (each call is a round trip). A `[branch]`
  ref returns its sub-refs to fetch next; every other ref returns its value.
- For an attachment body, fetch only `narrative` and `findings`. Never fetch `image_b64`
  — it is raw pixels you never read.
"""


def _build_agent():
    from langchain.agents import create_agent
    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=MODEL_VERSION, max_tokens=8000)
    middleware: list = []
    if CACHE_ENABLED:
        from .caching import PromptCachingMiddleware

        middleware.append(PromptCachingMiddleware())

    tools, system = TOOLS, SYSTEM_PROMPT
    if HALO_ENABLED:
        from halo_format_langgraph import install_halo

        installed = install_halo(tools=TOOLS, threshold=HALO_THRESHOLD)
        tools = installed.tools                          # TOOLS + halo_fetch
        middleware = [*middleware, *installed.middleware]  # + the wrap_tool_call encode middleware
        system = SYSTEM_PROMPT + HALO_GUIDANCE

    return create_agent(model, tools=tools, middleware=middleware, system_prompt=system)


async def run(claim_id: str) -> None:
    label = os.environ.get("RUN_LABEL", "halo" if HALO_ENABLED else "baseline")
    agent = _build_agent()
    prompt = (
        f"Adjudicate insurance claim {claim_id} end to end: decide each service line "
        f"(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, "
        f"record the decisions, open the review gate and wait for the examiner if required, then "
        f"post the adjudication. Finish with a one-line per-line summary."
    )
    print(f"=== Insurance Claim Decision Agent — LangGraph + Claude — {claim_id} (model {MODEL_VERSION}) ===\n")

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": MAX_STEPS},
    )

    usage = Counter()
    tools: Counter = Counter()
    for msg in result["messages"]:
        um = getattr(msg, "usage_metadata", None)
        if um:
            det = um.get("input_token_details") or {}
            cr = det.get("cache_read", 0) or 0
            # cache WRITES land under ephemeral_*_input_tokens in this langchain-anthropic version,
            # not cache_creation; fall back to those.
            cw = (det.get("cache_creation", 0) or 0) or (
                (det.get("ephemeral_5m_input_tokens", 0) or 0) + (det.get("ephemeral_1h_input_tokens", 0) or 0)
            )
            # langchain's input_tokens is the GRAND total (fresh + cache_read + cache_write); split out
            # the fresh (full-price) portion so the cost is not double-counted.
            usage["input_tokens"] += max(0, um.get("input_tokens", 0) - cr - cw)
            usage["output_tokens"] += um.get("output_tokens", 0)
            usage["cache_read"] += cr
            usage["cache_creation"] += cw
        for tc in getattr(msg, "tool_calls", None) or []:
            tools[tc["name"]] += 1
    print(getattr(result["messages"][-1], "content", "") or "")

    total = sum(usage.values())
    summary = {
        "label": label, "runtime": "langgraph", "halo": HALO_ENABLED, "cache": CACHE_ENABLED,
        "model": MODEL_VERSION,
        "tokens": dict(usage), "total_tokens": total, "estimated_cost_usd": _cost(usage, MODEL_VERSION),
        "tool_calls": dict(tools), "tool_call_total": sum(tools.values()),
    }
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{label}.json").write_text(json.dumps(summary, indent=2))
    print(f"\n=== {label} === tokens={total:,} cost=${summary['estimated_cost_usd']} "
          f"tool_calls={summary['tool_call_total']}")
    print(f"(written to runs/{label}.json)")


async def selftest(claim_id: str) -> None:
    from .tools import (
        payer_adjudicate_line,
        payer_get_agent_provenance,
        payer_get_attachment,
        payer_get_claim,
    )

    print("== LangGraph self-test (no API call) ==")
    prov = json.loads(await payer_get_agent_provenance.ainvoke({}))
    print("provenance tool ok:", prov["agent_id"])

    claim = json.loads(await payer_get_claim.ainvoke({"claim_id": claim_id}))
    manifest = claim.get("attachments", []) or []
    print(f"get_claim ok: {len(claim.get('lines', []))} lines, {len(manifest)} attachment(s) in "
          f"manifest, {len(json.dumps(claim))}B (light — refs + metadata, no bodies)")

    if manifest:
        ref = manifest[0]["ref"]
        body = json.loads(await payer_get_attachment.ainvoke({"claim_id": claim_id, "attachment_ref": ref}))
        print(f"get_attachment({ref}) ok: {len(json.dumps(body))}B body — image_b64 "
              f"{len(body.get('image_b64', ''))}B (heavy — for the Halo adapter to encode)")

    eng = json.loads(await payer_adjudicate_line.ainvoke({"claim_id": claim_id, "line_number": 1}))
    print(f"engine adjudicate_line(1): plan_paid={eng['plan_paid_cents']} review_required={eng['review_required']}")
    print(f"tools wired: {len(TOOLS)} LangChain tools")

    if HALO_ENABLED:
        from halo_format_langgraph import install_halo

        installed = install_halo(tools=TOOLS, threshold=HALO_THRESHOLD)
        names = [t.name for t in installed.tools]
        assert "halo_fetch" in names and installed.middleware, "halo wiring incomplete"
        print(f"halo wiring ok: +halo_fetch tool ({len(installed.tools)} total), "
              f"+{len(installed.middleware)} middleware (HALO on)")
    print("== self-test OK: LangChain tools + deterministic engine functional ==")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    cid = argv[0] if argv else "CLM-PROF"
    asyncio.run(selftest(cid) if "--selftest" in sys.argv else run(cid))
