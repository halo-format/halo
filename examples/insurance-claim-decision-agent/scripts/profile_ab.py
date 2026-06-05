"""Standalone A/B profiler: same claim, with vs without Halo.

Writes runs/prof_<label>.json after every streamed message (so a partial result
survives an interrupted run) and prints a one-line summary at the end. The arm is
chosen by HALO=0/1; everything else is identical.

    HALO=0 RUN_LABEL=baseline python -m scripts.profile_ab CLM-PROF
    HALO=1 RUN_LABEL=halo     python -m scripts.profile_ab CLM-PROF
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

import agent.main as m

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)


async def _safe_stream(agen):
    """Yield messages, swallowing the occasional benign SDK end-of-stream wrapper error
    so an interrupted tail does not discard the accumulated profile."""
    it = agen.__aiter__()
    while True:
        try:
            yield await it.__anext__()
        except StopAsyncIteration:
            return
        except Exception as e:  # noqa: BLE001 - profiling harness, keep partial data
            print(f"[profiler] stream ended early: {str(e)[:120]}")
            return


async def run(claim_id: str) -> None:
    from claude_agent_sdk import query

    halo = m.HALO_ENABLED
    label = os.environ.get("RUN_LABEL", "halo" if halo else "baseline")
    options, session = m.build_options(halo)

    tools: Counter = Counter()
    usage: dict = {}
    num_turns = None
    out_path = RUNS / f"prof_{label}.json"

    # Terse: adjudicate + record + post, then a single confirmation line (no long EOB),
    # so the run completes quickly and the comparison is about navigation, not prose.
    prompt = (
        f"Adjudicate claim {claim_id}: decide each line with the deterministic engine and the "
        f"standard reason codes, record the decisions with evidence, and post the adjudication. "
        f"All lines should auto-finalize (no human gate needed). After posting, reply with ONE "
        f"line: the per-line decisions and totals. Do NOT write a long EOB explanation."
    )

    def snapshot():
        halo_stats = None
        if session is not None:
            maps = getattr(session, "_maps", {})
            store = getattr(session, "store", None)
            try:
                nodes = len(store) if store is not None else None
            except TypeError:
                nodes = None
            halo_stats = {"maps_encoded": len(maps), "map_ids": list(maps.keys()),
                          "store_nodes": nodes}
        summary = {
            "label": label, "halo_enabled": halo, "model": m.MODEL_VERSION,
            "tokens": {
                "input": int(usage.get("input_tokens", 0) or 0),
                "output": int(usage.get("output_tokens", 0) or 0),
                "cache_read": int(usage.get("cache_read_input_tokens", 0) or 0),
                "cache_creation": int(usage.get("cache_creation_input_tokens", 0) or 0),
            },
            "num_turns": num_turns,
            "tool_calls": dict(tools),
            "tool_call_total": sum(tools.values()),
            "halo_fetch_calls": tools.get("mcp__halo__halo_fetch", 0),
            "halo": halo_stats,
        }
        summary["tokens"]["total"] = sum(summary["tokens"].values())
        out_path.write_text(json.dumps(summary, indent=2))
        return summary

    async for msg in _safe_stream(query(prompt=prompt, options=options)):
        for b in getattr(msg, "content", None) or []:
            if "ToolUse" in type(b).__name__:
                tools[getattr(b, "name", "?")] += 1
        if type(msg).__name__ == "ResultMessage":
            usage = getattr(msg, "usage", None) or {}
            num_turns = getattr(msg, "num_turns", None)
        snapshot()

    s = snapshot()
    t = s["tokens"]
    print(f"\n=== PROFILE [{label}] model={s['model']} ===")
    print(f"  input={t['input']:,} output={t['output']:,} cache_read={t['cache_read']:,} "
          f"cache_creation={t['cache_creation']:,} TOTAL={t['total']:,}")
    print(f"  turns={s['num_turns']}  tool_calls={s['tool_call_total']}  "
          f"halo_fetch={s['halo_fetch_calls']}")
    print(f"  tools={s['tool_calls']}")
    print(f"  halo={s['halo']}")
    print(f"  (written to {out_path})")


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "CLM-PROF"
    asyncio.run(run(cid))
