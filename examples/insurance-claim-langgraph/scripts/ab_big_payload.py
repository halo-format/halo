"""Big-payload A/B: baseline (raw JSON) vs Halo, on one large attachment body.

Self-contained — needs only ANTHROPIC_API_KEY (no database, no review gate). It builds a
single `get_attachment` tool that returns a realistic large dental attachment (small clinical
fields + a ~200KB raw `image_b64` blob, the size of a real intraoral X-ray), then asks the
model a question it can answer from the small fields alone. It runs the same task twice:

  baseline — the tool result lands in context whole; the 200KB blob is re-read every turn.
  halo     — install_halo encodes the result; the model sees a shape map and halo_fetches
             only `kind`/`findings`, so the blob never enters context.

This isolates Halo's per-payload context reduction (the reliable win) from the conversation
length: with a short conversation and a big payload, the input-token gap is dramatic. (In a
long agent loop without prompt caching the extra halo_fetch round trips can offset the saving
— see the README note — which is why this harness keeps the conversation short.)

    python -m scripts.ab_big_payload          # default ~200KB image
    IMAGE_KB=400 python -m scripts.ab_big_payload
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

from halo_format_langgraph import install_halo

load_dotenv()

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
IMAGE_KB = int(os.environ.get("IMAGE_KB", "200"))
CACHE_ENABLED = os.environ.get("CACHE", "").lower() in ("1", "true", "yes", "on")

HALO_GUIDANCE = (
    "\n\nLarge tool results come back as a Halo shape map (a `[halo] map …` note with one line "
    "per field: ref, kind, preview). Read the previews; for a field you still need call "
    "halo_fetch(refs=[...]) with an ARRAY of refs (batch them). Never fetch `image_b64`."
)

TASK = (
    "Fetch attachment ATT-BIG-02 and tell me: its kind, and whether its findings support a crown "
    "on tooth #19. Do not read or echo the image_b64 field. Answer in one sentence."
)


def _attachment_body() -> dict:
    """A realistic large attachment: small clinical fields + a big raw image blob."""
    blob = hashlib.sha256(b"CLM-BIG/ATT-BIG-02/image").digest()
    image_b64 = base64.b64encode(blob * (IMAGE_KB * 1024 // len(blob))).decode()
    return {
        "attachment_ref": "ATT-BIG-02", "claim_id": "CLM-BIG", "kind": "periapical_xray",
        "captured_at": "2026-05-18",
        "narrative": "Patient presents for crown prep on tooth #19. Deep restoration with recurrent decay.",
        "findings": "Deep carious lesion approximating the pulp; crown indicated to restore the tooth.",
        "tooth_chart": {str(t): "sound" for t in range(1, 33)},
        "image_meta": {"dpi": 300, "bytes": IMAGE_KB * 1024, "modality": "intraoral"},
        "image_b64": image_b64,  # raw pixels — large, not human-readable
    }


DOC = _attachment_body()


@tool
async def get_attachment(attachment_ref: str) -> str:
    """Fetch one clinical attachment body (narrative + findings + tooth chart + raw image) for review."""
    return json.dumps(DOC)


async def _run(halo: bool) -> dict:
    model = ChatAnthropic(model=MODEL, max_tokens=1000)
    middleware: list = []
    if CACHE_ENABLED:
        from agent.caching import PromptCachingMiddleware

        middleware.append(PromptCachingMiddleware())
    if halo:
        installed = install_halo(tools=[get_attachment], threshold=2048)
        agent = create_agent(model, tools=installed.tools,
                             middleware=[*middleware, *installed.middleware], system_prompt=HALO_GUIDANCE)
    else:
        agent = create_agent(model, tools=[get_attachment], middleware=middleware)

    result = await agent.ainvoke({"messages": [{"role": "user", "content": TASK}]},
                                 config={"recursion_limit": 30})
    tin = tout = cread = ccreate = calls = 0
    for m in result["messages"]:
        um = getattr(m, "usage_metadata", None)
        if um:
            det = um.get("input_token_details") or {}
            cr = det.get("cache_read", 0) or 0
            cw = (det.get("cache_creation", 0) or 0) or (
                (det.get("ephemeral_5m_input_tokens", 0) or 0) + (det.get("ephemeral_1h_input_tokens", 0) or 0)
            )
            # langchain's input_tokens is the grand total; keep only the fresh (full-price) portion.
            tin += max(0, um.get("input_tokens", 0) - cr - cw)
            tout += um.get("output_tokens", 0)
            cread += cr
            ccreate += cw
        calls += len(getattr(m, "tool_calls", None) or [])
    return {"input": tin, "output": tout, "cache_read": cread, "cache_creation": ccreate,
            "tool_calls": calls, "answer": (getattr(result["messages"][-1], "content", "") or "").strip()}


def _cost(r: dict) -> float:
    # sonnet-4-6 per-MTok: input 3, output 15, cache_read 0.3, cache_write 3.75
    m = 1_000_000
    return round(r["input"] * 3 / m + r["output"] * 15 / m
                 + r["cache_read"] * 0.3 / m + r["cache_creation"] * 3.75 / m, 6)


async def main() -> None:
    print(f"== Big-payload A/B (model {MODEL}, cache={'on' if CACHE_ENABLED else 'off'}) ==")
    print(f"payload: {len(json.dumps(DOC)):,}B  (image_b64 {len(DOC['image_b64']):,}B)\n")
    base = await _run(halo=False)
    halo = await _run(halo=True)
    for label, r in (("baseline", base), ("halo", halo)):
        print(f"{label:9}| input={r['input']:>8,}  output={r['output']:>5,}  "
              f"cache_read={r['cache_read']:>8,}  cache_write={r['cache_creation']:>8,}  "
              f"tools={r['tool_calls']}  cost=${_cost(r):.4f}")
    # "ingested" = tokens the model had to take in fresh (full price + cache writes); under caching
    # the blob shifts from input to cache_write, so raw input alone understates what baseline paid for.
    ingested = lambda r: r["input"] + r["cache_creation"]
    saved = 1 - ingested(halo) / ingested(base) if ingested(base) else 0
    cost_saved = 1 - _cost(halo) / _cost(base) if _cost(base) else 0
    print(f"\ncontext ingested (fresh+write): {ingested(base):,} -> {ingested(halo):,}  ({saved * 100:.0f}% less)")
    print(f"cost:                           ${_cost(base):.4f} -> ${_cost(halo):.4f}  ({cost_saved * 100:.0f}% less)")
    print(f"\nbaseline answer: {base['answer'][:140]}")
    print(f"halo answer:     {halo['answer'][:140]}")


if __name__ == "__main__":
    asyncio.run(main())
