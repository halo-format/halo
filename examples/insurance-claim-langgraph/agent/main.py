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


def _build_agent():
    from langchain.agents import create_agent
    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=MODEL_VERSION, max_tokens=8000)
    return create_agent(model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)


async def run(claim_id: str) -> None:
    label = os.environ.get("RUN_LABEL", "langgraph")
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
            usage["input_tokens"] += um.get("input_tokens", 0)
            usage["output_tokens"] += um.get("output_tokens", 0)
            det = um.get("input_token_details") or {}
            usage["cache_read"] += det.get("cache_read", 0) or 0
            usage["cache_creation"] += det.get("cache_creation", 0) or 0
        for tc in getattr(msg, "tool_calls", None) or []:
            tools[tc["name"]] += 1
    print(getattr(result["messages"][-1], "content", "") or "")

    total = sum(usage.values())
    summary = {
        "label": label, "runtime": "langgraph", "model": MODEL_VERSION,
        "tokens": dict(usage), "total_tokens": total, "estimated_cost_usd": _cost(usage, MODEL_VERSION),
        "tool_calls": dict(tools), "tool_call_total": sum(tools.values()),
    }
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{label}.json").write_text(json.dumps(summary, indent=2))
    print(f"\n=== {label} === tokens={total:,} cost=${summary['estimated_cost_usd']} "
          f"tool_calls={summary['tool_call_total']}")
    print(f"(written to runs/{label}.json)")


async def selftest(claim_id: str) -> None:
    from .tools import payer_adjudicate_line, payer_get_agent_provenance, payer_get_claim

    print("== LangGraph self-test (no API call) ==")
    prov = json.loads(await payer_get_agent_provenance.ainvoke({}))
    print("provenance tool ok:", prov["agent_id"])
    claim = json.loads(await payer_get_claim.ainvoke({"claim_id": claim_id}))
    print(f"get_claim ok: {len(claim.get('lines', []))} lines, "
          f"{len(json.dumps(claim))}B payload (heavy — for the Halo adapter to encode)")
    eng = json.loads(await payer_adjudicate_line.ainvoke({"claim_id": claim_id, "line_number": 1}))
    print(f"engine adjudicate_line(1): plan_paid={eng['plan_paid_cents']} review_required={eng['review_required']}")
    print(f"tools wired: {len(TOOLS)} LangChain tools")
    print("== self-test OK: LangChain tools + deterministic engine functional ==")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    cid = argv[0] if argv else "CLM-PROF"
    asyncio.run(selftest(cid) if "--selftest" in sys.argv else run(cid))
