"""Run the insurance-claim agent on the OpenAI Agents SDK, natively against an OpenAI model.

`Runner.run` drives the model-calls-tools loop over the 15 payer tools, with an `Agent`
configured for `gpt-4.1`. The deterministic engine, the human-review gate, and the reason
codes are reused unchanged from the other ports — only the harness is the OpenAI Agents SDK.

    python -m agent.main CLM-PROF          # adjudicate a claim end to end
    python -m agent.main CLM-PROF --selftest   # tool dispatch + engine, no API key

This example ships WITHOUT a Halo integration by default — tools return plain JSON. HALO=1
attaches the Halo OpenAI-Agents host adapter (`halo_format_openai.install_halo`): a
`call_model_input_filter` swaps a large tool result for a shape map before the model sees
it, and a `halo_fetch` tool pulls back only the fields the model needs. Navigation guidance
rides in the instructions (prompt mode). The payload it earns its keep on is the on-demand
attachment body from `payer_get_attachment` — narrative/findings the reviewer reads, plus a
bulky `image_b64` blob it never reads.

Requires OPENAI_API_KEY and a seeded mimic_payer database. For a claim with adverse lines
(CLM-1001), run scripts/reviewer_console.py in a second terminal.
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
MAX_STEPS = int(os.environ.get("MAX_TURNS", "120"))

# OpenAI per-MTok pricing (USD). `cached` is the discounted rate for the cached prompt
# prefix — OpenAI caches automatically, with no write premium (unlike Anthropic), so there
# is no separate CACHE toggle in this port.
PRICING = {
    "gpt-4.1": {"in": 2.00, "out": 8.00, "cached": 0.50},
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60, "cached": 0.10},
    "gpt-4o": {"in": 2.50, "out": 10.00, "cached": 1.25},
    "gpt-5": {"in": 1.25, "out": 10.00, "cached": 0.125},
}


def _cost(u: dict, model: str):
    p = PRICING.get(model)
    if not p:
        return None
    m = 1_000_000
    fresh = max(0, u.get("input_tokens", 0) - u.get("cached_tokens", 0))
    return round(fresh * p["in"] / m + u.get("cached_tokens", 0) * p["cached"] / m
                 + u.get("output_tokens", 0) * p["out"] / m, 6)


# ── Halo toggle ───────────────────────────────────────────────────────────────
# HALO=1 attaches the Halo OpenAI-Agents adapter: a call_model_input_filter encodes any
# large tool result (the on-demand attachment body) into a content-addressed store and hands
# the model a shape map, plus a halo_fetch tool to pull back only the fields it needs.
# Guidance rides in the instructions (prompt mode) — no skills system needed.
HALO_ENABLED = os.environ.get("HALO", "").lower() in ("1", "true", "yes", "on")
HALO_THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))

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


def _build(claim_id: str):
    """Build the Agent and the RunConfig. Returns (agent, run_config, prompt)."""
    from agents import Agent, RunConfig

    tools, instructions, run_config = TOOLS, SYSTEM_PROMPT, RunConfig()
    if HALO_ENABLED:
        from halo_format_openai import install_halo

        installed = install_halo(tools=TOOLS, threshold=HALO_THRESHOLD)
        tools = installed.tools                                  # TOOLS + halo_fetch
        instructions = SYSTEM_PROMPT + HALO_GUIDANCE
        run_config = RunConfig(call_model_input_filter=installed.call_model_input_filter)

    agent = Agent(name="insurance-claim-decision-agent", instructions=instructions,
                  tools=tools, model=MODEL_VERSION)
    prompt = (
        f"Adjudicate insurance claim {claim_id} end to end: decide each service line "
        f"(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, "
        f"record the decisions, open the review gate and wait for the examiner if required, then "
        f"post the adjudication. Finish with a one-line per-line summary."
    )
    return agent, run_config, prompt


async def run(claim_id: str) -> None:
    from agents import Runner

    label = os.environ.get("RUN_LABEL", "halo" if HALO_ENABLED else "baseline")
    agent, run_config, prompt = _build(claim_id)
    print(f"=== Insurance Claim Decision Agent — OpenAI Agents SDK — {claim_id} (model {MODEL_VERSION}) ===\n")

    result = await Runner.run(agent, prompt, run_config=run_config, max_turns=MAX_STEPS)

    # Token usage from the run's shared usage accumulator; tool calls from the run items.
    u = result.context_wrapper.usage
    usage = {
        "input_tokens": u.input_tokens,
        "cached_tokens": getattr(u.input_tokens_details, "cached_tokens", 0) or 0,
        "output_tokens": u.output_tokens,
    }
    tools: Counter = Counter()
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_item":
            tools[getattr(item.raw_item, "name", "?")] += 1
    print(result.final_output or "")

    total = u.total_tokens
    summary = {
        "label": label, "runtime": "openai_agents", "halo": HALO_ENABLED, "model": MODEL_VERSION,
        "tokens": usage, "total_tokens": total, "estimated_cost_usd": _cost(usage, MODEL_VERSION),
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

    print("== OpenAI Agents self-test (no API call) ==")
    prov = json.loads(await payer_get_agent_provenance())
    print("provenance tool ok:", prov["agent_id"])

    claim = json.loads(await payer_get_claim(claim_id))
    manifest = claim.get("attachments", []) or []
    print(f"get_claim ok: {len(claim.get('lines', []))} lines, {len(manifest)} attachment(s) in "
          f"manifest, {len(json.dumps(claim))}B (light — refs + metadata, no bodies)")

    if manifest:
        ref = manifest[0]["ref"]
        body = json.loads(await payer_get_attachment(claim_id, ref))
        print(f"get_attachment({ref}) ok: {len(json.dumps(body))}B body — image_b64 "
              f"{len(body.get('image_b64', ''))}B (heavy — for the Halo adapter to encode)")

    eng = json.loads(await payer_adjudicate_line(claim_id, 1))
    print(f"engine adjudicate_line(1): plan_paid={eng['plan_paid_cents']} review_required={eng['review_required']}")
    print(f"tools wired: {len(TOOLS)} function tools")

    if HALO_ENABLED:
        from halo_format_openai import install_halo

        installed = install_halo(tools=TOOLS, threshold=HALO_THRESHOLD)
        names = [t.name for t in installed.tools]
        assert "halo_fetch" in names and callable(installed.call_model_input_filter), "halo wiring incomplete"
        print(f"halo wiring ok: +halo_fetch tool ({len(installed.tools)} total), "
              f"+call_model_input_filter (HALO on)")
    print("== self-test OK: function tools + deterministic engine functional ==")


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    cid = argv[0] if argv else "CLM-PROF"
    asyncio.run(selftest(cid) if "--selftest" in sys.argv else run(cid))
