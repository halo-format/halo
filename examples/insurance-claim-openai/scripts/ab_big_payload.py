"""Big-payload A/B: baseline (raw JSON) vs Halo, on one large attachment body.

Self-contained — needs only OPENAI_API_KEY (no database, no review gate). It builds a single
`get_attachment` tool that returns a realistic large dental attachment (small clinical fields
+ a ~200KB raw `image_b64` blob, the size of a real intraoral X-ray), then asks the model a
question it can answer from the small fields alone. It runs the same task twice:

  baseline — the tool result lands in context whole; the 200KB blob is in the prompt each turn.
  halo     — install_halo's call_model_input_filter encodes the result; the model sees a shape
             map and halo_fetches only `kind`/`findings`, so the blob never enters context.

This isolates Halo's per-payload context reduction (the reliable win) from the conversation
length: with a short conversation and a big payload, the input-token gap is dramatic. (In a
long agent loop the extra halo_fetch round trips can offset the saving — see the README note —
which is why this harness keeps the conversation short. OpenAI caches the prompt prefix
automatically, so a re-read blob is cheaper than full price but never free.)

    python -m scripts.ab_big_payload          # default ~200KB image
    IMAGE_KB=400 python -m scripts.ab_big_payload
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os

from agents import Agent, RunConfig, Runner, function_tool
from dotenv import load_dotenv

from halo_format_openai import install_halo

load_dotenv()

MODEL = os.environ.get("AGENT_MODEL", "gpt-4.1")
IMAGE_KB = int(os.environ.get("IMAGE_KB", "200"))

# gpt-4.1 per-MTok: input 2.00, output 8.00, cached input 0.50.
PRICE = {"in": 2.00, "out": 8.00, "cached": 0.50}

HALO_GUIDANCE = (
    "Large tool results come back as a Halo shape map (a `[halo] map …` note with one line "
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


async def get_attachment(attachment_ref: str) -> str:
    """Fetch one clinical attachment body (narrative + findings + tooth chart + raw image) for review."""
    return json.dumps(DOC)


async def _run(halo: bool) -> dict:
    base_tool = function_tool(get_attachment)
    if halo:
        installed = install_halo(tools=[base_tool], threshold=2048)
        agent = Agent(name="ab", instructions=HALO_GUIDANCE, tools=installed.tools, model=MODEL)
        run_config = RunConfig(call_model_input_filter=installed.call_model_input_filter)
    else:
        agent = Agent(name="ab", instructions="", tools=[base_tool], model=MODEL)
        run_config = RunConfig()

    result = await Runner.run(agent, TASK, run_config=run_config, max_turns=30)
    u = result.context_wrapper.usage
    cached = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
    calls = sum(1 for it in result.new_items if getattr(it, "type", None) == "tool_call_item")
    return {"input": u.input_tokens, "cached": cached, "output": u.output_tokens,
            "tool_calls": calls, "answer": (result.final_output or "").strip()}


def _cost(r: dict) -> float:
    m = 1_000_000
    fresh = max(0, r["input"] - r["cached"])
    return round(fresh * PRICE["in"] / m + r["cached"] * PRICE["cached"] / m + r["output"] * PRICE["out"] / m, 6)


async def main() -> None:
    print(f"== Big-payload A/B (model {MODEL}) ==")
    print(f"payload: {len(json.dumps(DOC)):,}B  (image_b64 {len(DOC['image_b64']):,}B)\n")
    base = await _run(halo=False)
    halo = await _run(halo=True)
    for label, r in (("baseline", base), ("halo", halo)):
        print(f"{label:9}| input={r['input']:>8,}  cached={r['cached']:>8,}  output={r['output']:>5,}  "
              f"tools={r['tool_calls']}  cost=${_cost(r):.4f}")
    # "ingested" = fresh (full-price) input tokens — what the model had to take in new. Under OpenAI's
    # automatic caching the re-read blob shifts to `cached`, so fresh input is the honest comparison.
    ingested = lambda r: max(0, r["input"] - r["cached"])
    saved = 1 - ingested(halo) / ingested(base) if ingested(base) else 0
    cost_saved = 1 - _cost(halo) / _cost(base) if _cost(base) else 0
    print(f"\ncontext ingested (fresh input): {ingested(base):,} -> {ingested(halo):,}  ({saved * 100:.0f}% less)")
    print(f"cost:                           ${_cost(base):.4f} -> ${_cost(halo):.4f}  ({cost_saved * 100:.0f}% less)")
    print(f"\nbaseline answer: {base['answer'][:140]}")
    print(f"halo answer:     {halo['answer'][:140]}")


if __name__ == "__main__":
    asyncio.run(main())
