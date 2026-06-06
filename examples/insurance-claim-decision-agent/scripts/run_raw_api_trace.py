"""Run the insurance agent on the RAW Claude Messages API and write a FULL trace.

This is the demonstrator behind the landing page. It drives the *published*
``halo_format_claude.raw`` adapter (create_raw_halo) through a hand-built tool-use
loop on ``anthropic.messages.create`` — exactly like ``scripts/run_raw_api.py`` —
but records every observable step into a structured artifact you can render:

  • each Claude API turn  — usage, stop_reason, assistant text, the tool_use calls;
  • each tool result      — the full payload bytes, and (when Halo encodes it) the
                            content-addressed NODE TREE: every handle, its kind, its
                            summary/value, and a re-computed hash check proving the
                            handle verifies (this is "how Halo hashes a tool result");
  • the SHAPE MAP         — the small map the model actually saw, with the byte saving;
  • each halo_fetch       — the refs asked for, the handle each resolved to, the
                            verified-on-read result the model got back.

Outputs (under ./runs):
  trace_<label>.json   the full structured trace
  trace_<label>.md     a human-readable rendering for the landing page

    set -a && . ./.env && set +a
    python -m scripts.run_raw_api_trace CLM-PROF
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

# Published core + adapter — the same handles every Halo port produces.
from halo_format import decode, hash_bytes, is_branch
from halo_format_claude.raw import create_raw_halo

# Reuse the raw-loop's tool definitions / dispatch / pricing verbatim.
from scripts.run_raw_api import DISPATCH, TOOL_DEFS, _cost, build_tools

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))
MAX_TURNS = int(os.environ.get("RAW_MAX_TURNS", "40"))
DOMAIN_HINT = (
    "\nFor a claim, fetch the service `lines` from the map. For a line needing documentation review "
    "(major restorative, endodontic, periodontal, oral surgery), call payer_get_attachment for its "
    "supporting attachment and read ONLY `narrative` and `findings` — never fetch `image_b64` (raw "
    "pixels: large and unreadable). Routine preventive/basic lines need no attachment."
)
PREVIEW = 240


def _preview(value, n: int = PREVIEW) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def dump_node_tree(store, root: str, alg: str) -> list[dict]:
    """Walk the content-addressed tree from `root`, recording every node + a hash check.

    For each reachable handle: decode the stored bytes, re-hash them under `alg`, and
    record whether the recomputed digest equals the handle (the verified-read property
    the navigator enforces on every fetch). Branch nodes list their child handles; leaf
    nodes carry a bounded preview of the value and its byte size.
    """
    nodes: list[dict] = []
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(root, 0)]
    while queue:
        handle, depth = queue.pop(0)
        if handle in seen:
            continue
        seen.add(handle)
        raw = store.get(handle)
        node = decode(raw)
        entry = {
            "handle": handle,
            "depth": depth,
            "stored_bytes": len(raw),
            # The integrity proof: handle == hash(canonical(node)). Recompute and compare.
            "verified": hash_bytes(raw, alg) == handle,
        }
        if is_branch(node):
            entry["kind"] = "branch"
            entry["summary"] = node.get("summary")
            entry["branches"] = dict(node.get("branches", {}))
            for child in node.get("branches", {}).values():
                queue.append((child, depth + 1))
        else:
            entry["kind"] = "leaf"
            value = node.get("value")
            entry["value_bytes"] = len(json.dumps(value, default=str))
            entry["value_preview"] = _preview(value)
        nodes.append(entry)
    return nodes


async def run(claim_id: str) -> None:
    import anthropic

    halo = os.environ.get("HALO", "1").lower() in ("1", "true", "yes", "on")
    label = os.environ.get("RUN_LABEL", f"raw_{'halo' if halo else 'baseline'}_{claim_id}")
    client = anthropic.AsyncAnthropic()
    adapter = create_raw_halo(threshold=THRESHOLD) if halo else None
    store = adapter.session.store if adapter else None
    alg = adapter.session._alg if adapter else "sha256"  # the bound hash algorithm

    # The ONLY differences between the arms: the guidance line, the halo_fetch tool, and whether a
    # large tool result is encoded to a shape map or returned in full. Everything else is identical,
    # so the two traces are directly comparable.
    system_text = SYSTEM_PROMPT + ((adapter.guidance + DOMAIN_HINT) if adapter else "")
    system = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]
    tools = build_tools(adapter.tool_def if adapter else None)
    prompt = (
        f"Adjudicate insurance claim {claim_id} end to end: decide each service line "
        f"(pay/deny/reduce/pend) with the deterministic engine and the standard reason codes, "
        f"record the decisions with evidence, open the review gate and wait for the examiner if "
        f"required, then post the adjudication. Finish with a one-line per-line summary."
    )
    messages: list[dict] = [{"role": "user", "content": prompt}]

    trace: dict = {
        "meta": {
            "runtime": "raw_messages_api",
            "model": MODEL_VERSION,
            "claim_id": claim_id,
            "halo_enabled": halo,
            "halo_threshold_bytes": THRESHOLD,
            "adapter": "halo_format_claude.raw.create_raw_halo" if halo else None,
            "alg": alg,
            "system_prompt_chars": len(system_text),
            "tool_count": len(tools),
        },
        "turns": [],
        "tool_results": [],
        "fetches": [],
    }

    usage = Counter()
    tool_calls: Counter = Counter()
    turns = 0

    print(f"=== TRACE — Insurance Claim Decision Agent — RAW Claude API — {claim_id} "
          f"— {'HALO' if halo else 'BASELINE'} (model {MODEL_VERSION}) ===\n", flush=True)

    while turns < MAX_TURNS:
        turns += 1
        resp = await client.messages.create(
            model=MODEL_VERSION, max_tokens=8000, system=system, tools=tools, messages=messages,
        )
        turn_usage = {k: getattr(resp.usage, k, 0) or 0 for k in
                      ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        for k, v in turn_usage.items():
            usage[k] += v

        texts, tool_uses = [], []
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                texts.append(block.text)
                print(block.text, flush=True)
            elif block.type == "tool_use":
                tool_calls[block.name] += 1
                tool_uses.append({"id": block.id, "name": block.name, "input": dict(block.input)})
                print(f"  → {block.name} {json.dumps(block.input)[:120]}", flush=True)

        trace["turns"].append({
            "index": turns,
            "stop_reason": resp.stop_reason,
            "usage": turn_usage,
            "assistant_text": texts,
            "tool_uses": tool_uses,
        })

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            name, args = block.name, dict(block.input)
            try:
                if adapter and adapter.is_fetch(name):
                    # ── a halo_fetch call: record refs → resolved handle → verified result ──
                    text = adapter.fetch(args["refs"])
                    parsed = json.loads(text)
                    fetch_rec = {"turn": turns, "refs": args["refs"], "results": []}
                    for ref, entry in parsed.items():
                        rec = {"ref": ref}
                        try:
                            rec["resolved_handle"] = adapter.session._navigator.resolve(ref)
                        except Exception:
                            rec["resolved_handle"] = None
                        rec["ok"] = bool(entry.get("ok"))
                        if entry.get("ok") and "value" in entry:
                            rec["kind"] = "leaf"
                            rec["value_bytes"] = len(json.dumps(entry["value"], default=str))
                            rec["value_preview"] = _preview(entry["value"])
                        elif entry.get("ok"):
                            rec["kind"] = entry.get("kind", "branch")
                            rec["sub_fields"] = entry.get("fields")
                        else:
                            rec["error"] = entry.get("error")
                        # independent re-verification of the handle the model trusted
                        if rec.get("resolved_handle"):
                            try:
                                rec["reverified"] = hash_bytes(store.get(rec["resolved_handle"]), alg) == rec["resolved_handle"]
                            except Exception:
                                rec["reverified"] = None
                        fetch_rec["results"].append(rec)
                    trace["fetches"].append(fetch_rec)
                else:
                    # ── a domain tool: run it, then encode-or-passthrough (halo) or return full (baseline) ──
                    result = await DISPATCH[name](**args)
                    full = json.dumps(result, default=str)
                    text = adapter.encode_result(name, args, result) if adapter else full
                    encoded = text is not None and text.startswith("[halo]")
                    # "large" = what Halo targets (>= threshold); in baseline these enter context in full.
                    is_large = len(full) >= THRESHOLD
                    tr = {
                        "turn": turns, "tool": name, "args": args,
                        "full_bytes": len(full), "encoded": encoded,
                        "large": is_large,
                        "in_context_bytes": len(text),  # what actually went into the model's context
                    }
                    if encoded:
                        # the map this result folded into (argJoin keys on the id argument)
                        map_id = adapter.session._key_of(name, args) or "?"
                        env = adapter.session._maps.get(map_id)
                        tr["map_id"] = map_id
                        tr["shape_map_model_saw"] = text
                        tr["shape_map_bytes"] = len(text)
                        tr["reduction_pct"] = round(100 * (1 - len(text) / max(1, len(full))), 1)
                        tr["bytes_kept_out_of_context"] = len(full) - len(text)
                        if env is not None:
                            tr["envelope"] = {
                                "halo": env.get("halo"), "alg": env.get("alg"),
                                "root": env.get("root"),
                                "source": env.get("source"),
                                "view": {
                                    "summary": env["view"]["summary"],
                                    "branches": dict(env["view"]["branches"]),
                                },
                            }
                            nodes = dump_node_tree(store, env["root"], alg)
                            tr["nodes"] = nodes
                            tr["node_count"] = len(nodes)
                            tr["all_nodes_verified"] = all(n["verified"] for n in nodes)
                            tr["store_bytes_total"] = sum(n["stored_bytes"] for n in nodes)
                    trace["tool_results"].append(tr)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
            except Exception as e:
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"error: {e}", "is_error": True})
        messages.append({"role": "user", "content": results})

    # ── tally, over the LARGE tool results (>= threshold) — the bytes Halo targets ──
    # Both arms measure the same population, so bytes_full_total is identical across them and
    # bytes_in_context_total tells the story: full payload in baseline, shape map under Halo.
    large = [t for t in trace["tool_results"] if t.get("large")]
    bytes_full = sum(t["full_bytes"] for t in large)
    bytes_in_context = sum(t["in_context_bytes"] for t in large)

    trace["summary"] = {
        "label": label,
        "halo_enabled": halo,
        "tokens": dict(usage),
        "total_tokens": sum(usage.values()),
        "estimated_cost_usd": _cost(usage, MODEL_VERSION),
        "turns": turns,
        "tool_calls": dict(tool_calls),
        "halo_fetch_calls": tool_calls.get("halo_fetch", 0),
        "halo_maps": len(getattr(adapter.session, "_maps", {})) if adapter else 0,
        "encoded_results": sum(1 for t in trace["tool_results"] if t.get("encoded")),
        "large_results": len(large),
        "bytes_full_total": bytes_full,
        "bytes_in_context_total": bytes_in_context,
        "bytes_kept_out_of_context": bytes_full - bytes_in_context,
        "context_reduction_pct": round(100 * (1 - bytes_in_context / bytes_full), 1) if bytes_full else 0.0,
    }

    RUNS.mkdir(exist_ok=True)
    (RUNS / f"trace_{label}.json").write_text(json.dumps(trace, indent=2, default=str))
    (RUNS / f"trace_{label}.md").write_text(render_markdown(trace))
    s = trace["summary"]
    print(f"\n=== {label} === tokens={s['total_tokens']:,} cost=${s['estimated_cost_usd']} "
          f"turns={s['turns']} halo_fetch={s['halo_fetch_calls']} "
          f"encoded={s['encoded_results']} kept_out_of_context={s['bytes_kept_out_of_context']:,}B "
          f"({s['context_reduction_pct']}%)")
    print(f"(trace → runs/trace_{label}.json  +  runs/trace_{label}.md)")


def render_markdown(trace: dict) -> str:
    m, s = trace["meta"], trace["summary"]
    halo = m["halo_enabled"]
    arm = "HALO" if halo else "BASELINE (no Halo)"
    out: list[str] = []
    out.append(f"# Halo raw-API trace — claim {m['claim_id']} — {arm}\n")
    out.append(f"Runtime **{m['runtime']}** · model **{m['model']}** · "
               f"adapter `{m['adapter']}` · alg `{m['alg']}` · threshold {m['halo_threshold_bytes']} B\n")
    out.append("## Headline\n")
    if halo:
        out.append(f"- Encoded **{s['encoded_results']}** large tool result(s) into content-addressed maps.\n"
                   f"- Model saw **{s['bytes_in_context_total']:,} B** of shape maps instead of "
                   f"**{s['bytes_full_total']:,} B** of payload → **{s['bytes_kept_out_of_context']:,} B kept out "
                   f"of context** ({s['context_reduction_pct']}% smaller).\n"
                   f"- **{s['halo_fetch_calls']}** halo_fetch call(s); every fetched handle re-verified on read.\n")
    else:
        out.append(f"- **No Halo.** All **{s['large_results']}** large tool result(s) "
                   f"(**{s['bytes_full_total']:,} B**) entered the model's context **in full** and were "
                   f"re-sent every subsequent turn.\n"
                   f"- Nothing kept out of context; no content-addressed handles; no verified-on-read fetches.\n")
    out.append(f"- {s['total_tokens']:,} tokens · ${s['estimated_cost_usd']} · {s['turns']} turns.\n")

    if halo:
        out.append("\n## Tool results — how Halo hashes each payload\n")
        for t in trace["tool_results"]:
            if not t.get("encoded"):
                out.append(f"- `{t['tool']}` → {t['full_bytes']} B, below threshold, passed through.\n")
                continue
            env = t.get("envelope", {})
            out.append(f"### `{t['tool']}`  (map `{t.get('map_id')}`)\n")
            out.append(f"- payload **{t['full_bytes']:,} B** → shape map **{t['shape_map_bytes']:,} B** "
                       f"(**{t['reduction_pct']}%** smaller)\n")
            out.append(f"- root handle `{env.get('root','?')}` · {t.get('node_count')} nodes · "
                       f"all verified: **{t.get('all_nodes_verified')}**\n")
            out.append("\n**Shape map the model saw:**\n\n```\n" + t["shape_map_model_saw"] + "\n```\n")
            out.append("\n**Content-addressed node tree (handle → kind → verified):**\n\n```\n")
            for n in t.get("nodes", []):
                pad = "  " * n["depth"]
                tick = "✓" if n["verified"] else "✗"
                if n["kind"] == "branch":
                    out.append(f"{pad}{tick} {n['handle']}  [branch] {n.get('summary','')}\n")
                else:
                    out.append(f"{pad}{tick} {n['handle']}  [leaf {n.get('value_bytes')}B] {n.get('value_preview','')}\n")
            out.append("```\n")
    else:
        out.append("\n## Tool results — full payloads in context (no Halo)\n")
        for t in trace["tool_results"]:
            tag = "  ← LARGE, in context in full" if t.get("large") else ""
            out.append(f"- `{t['tool']}` → **{t['full_bytes']:,} B** in context{tag}\n")

    if trace["fetches"]:
        out.append("\n## halo_fetch calls — verified navigation\n")
        for f in trace["fetches"]:
            out.append(f"- turn {f['turn']}: fetch {json.dumps(f['refs'])}\n")
            for r in f["results"]:
                tick = "✓" if r.get("reverified") else ("?" if r.get("reverified") is None else "✗")
                if r.get("kind") == "leaf":
                    out.append(f"    {tick} `{r['ref']}` → `{r.get('resolved_handle')}` "
                               f"({r.get('value_bytes')}B): {r.get('value_preview','')}\n")
                elif r.get("ok"):
                    out.append(f"    {tick} `{r['ref']}` → branch, sub-refs returned\n")
                else:
                    out.append(f"    ✗ `{r['ref']}` → {r.get('error')}\n")

    out.append("\n## Per-turn API usage\n")
    for tn in trace["turns"]:
        u = tn["usage"]
        calls = ", ".join(tu["name"] for tu in tn["tool_uses"]) or "—"
        out.append(f"- turn {tn['index']} ({tn['stop_reason']}): "
                   f"in {u['input_tokens']} / out {u['output_tokens']} / "
                   f"cache_read {u['cache_read_input_tokens']} · tools: {calls}\n")
    return "".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cid = args[0] if args else "CLM-PROF"
    asyncio.run(run(cid))
