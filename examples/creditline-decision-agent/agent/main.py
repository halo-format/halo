"""Live Credit-Line Decision Agent on the Claude Agent SDK.

Registers the `mimic-creditline` MCP server as an external stdio subprocess,
loads the project Skills (intake / scoring / decisioning), and runs one
credit-line request end to end — including blocking on the human-in-the-loop
approval gate when the decision requires it.

    python -m agent.main [REQUEST_ID]

Token accounting is always on: every run prints a TOKENS summary (input / output
/ cache / total + cost + turns + per-tool call counts) and writes it to
``runs/<label>.json``.

Set ``HALO=1`` to route every tool result through the Halo adapter
(``halo_format_claude.install_halo``): large results are encoded into a
content-addressed map that stays out of the model's context, and the agent pulls
back only the fields it needs via the in-process ``halo_walk`` / ``halo_fetch``
tools. Run with and without it to compare token usage.

Requires ANTHROPIC_API_KEY and a seeded mimic_creditline database. Resolve any
pending approval from a second terminal with scripts/officer_console.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from .prompts import AGENT_ID, AGENT_VERSION, MODEL_VERSION, SYSTEM_PROMPT

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_REQUEST_ID = "11111111-1111-1111-1111-111111111111"

HALO_ENABLED = os.environ.get("HALO", "").lower() in ("1", "true", "yes", "on")
HALO_THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))
# How the model gets the navigation guidance when Halo is on: "skill" (a project Skill, loaded via
# the SDK skills option) or "prompt" (appended to the system prompt — no Skill listing or load turn).
HALO_GUIDANCE_MODE = os.environ.get("HALO_GUIDANCE_MODE", "skill").lower()
RUN_LABEL = os.environ.get("RUN_LABEL", "halo" if HALO_ENABLED else "baseline")

MCP_TOOLS = [
    "mcp__mimic-creditline__creditline_get_agent_provenance",
    "mcp__mimic-creditline__creditline_get_request",
    "mcp__mimic-creditline__creditline_get_customer",
    "mcp__mimic-creditline__creditline_pull_bureau",
    "mcp__mimic-creditline__creditline_get_active_policy",
    "mcp__mimic-creditline__creditline_record_decision",
    "mcp__mimic-creditline__creditline_request_approval",
    "mcp__mimic-creditline__creditline_notify_customer",
]

HALO_TOOLS = ["mcp__halo__halo_walk", "mcp__halo__halo_fetch"]

# Project Skills. The halo skill (navigation guidance) is enabled ONLY for the Halo run (and only in
# "skill" guidance mode) via the SDK `skills` option — the encode hook is the plumbing, the Skill is
# the guidance (halo-claude-sdk-integration.md §6).
BASE_SKILLS = ["intake", "scoring", "decisioning"]

# Same navigation guidance as the halo Skill, for "prompt" mode — appended to the system prompt so it
# rides in the (cached) prefix with no Skill listing entry and no Skill-load turn.
HALO_GUIDANCE = """

## Halo: navigating large tool results

Some tool results come back not as the full payload but as a *halo envelope* — a compact map
`{ "halo": "1", "view": { "summary", "branches": { name: handle } }, "source": { "id": "<mapId>" } }`;
the data is held, verified, in a store out of your context. When you receive one: read
`view.summary` and the branch names, then fetch ONLY the fields you need in a single
`mcp__halo__halo_fetch` call, passing a list of refs like `["<mapId>.credit_score", ...]` (batch
them; each value is verified). Use `mcp__halo__halo_walk` on a ref first only if a branch is itself
large. For a bureau report fetch `credit_score`, `total_outstanding_debt`, `delinquencies_24m`,
`hard_inquiries_6m`, `bureau_report_id` — not the `tradelines`/`recent_inquiries`/`public_records`
bulk. Use fetched values as if returned inline.
"""


def build_options(halo: bool):
    """Return (options, session). session is the HaloSession when halo is on, else None."""
    from claude_agent_sdk import ClaudeAgentOptions

    mcp_env = {
        "MIMIC_DB_DSN": os.environ["MIMIC_DB_DSN"],
        "APPROVAL_TIMEOUT_SECONDS": os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"),
        "APPROVAL_POLL_SECONDS": os.environ.get("APPROVAL_POLL_SECONDS", "2"),
        "BUREAU_TRADELINES": os.environ.get("BUREAU_TRADELINES", "0"),
        "PATH": os.environ.get("PATH", ""),
    }

    use_skill = halo and HALO_GUIDANCE_MODE == "skill"
    use_prompt = halo and HALO_GUIDANCE_MODE == "prompt"

    options = ClaudeAgentOptions(
        model=MODEL_VERSION,
        system_prompt=SYSTEM_PROMPT + (HALO_GUIDANCE if use_prompt else ""),
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        skills=BASE_SKILLS + (["halo"] if use_skill else []),
        allowed_tools=MCP_TOOLS + (HALO_TOOLS if halo else []),
        thinking={"type": "adaptive", "display": "summarized"},
        permission_mode="bypassPermissions",
        mcp_servers={
            "mimic-creditline": {
                "command": sys.executable,
                "args": ["-m", "mcp_servers.mimic_creditline.server"],
                "env": mcp_env,
            }
        },
    )

    if not halo:
        return options, None

    from halo_format_claude import install_halo

    result = install_halo(options, threshold=HALO_THRESHOLD)
    return result.options, result.session


class TokenMeter:
    """Tallies token usage and per-tool call counts from the streamed SDK messages."""

    def __init__(self) -> None:
        self.usage: dict = {}
        self.cost_usd: float | None = None
        self.num_turns: int | None = None
        self.tool_calls: Counter = Counter()
        self.final_text: str | None = None
        self.is_error: bool = False

    def observe(self, message) -> None:
        cls = type(message).__name__
        for block in getattr(message, "content", None) or []:
            if "ToolUse" in type(block).__name__:
                self.tool_calls[getattr(block, "name", "?")] += 1
        if cls == "ResultMessage":
            self.usage = getattr(message, "usage", None) or {}
            self.cost_usd = getattr(message, "total_cost_usd", None)
            self.num_turns = getattr(message, "num_turns", None)
            self.is_error = bool(getattr(message, "is_error", False))
            self.final_text = getattr(message, "result", None)

    # ── derived totals ────────────────────────────────────────────────────────
    @property
    def input_tokens(self) -> int:
        return int(self.usage.get("input_tokens", 0) or 0)

    @property
    def output_tokens(self) -> int:
        return int(self.usage.get("output_tokens", 0) or 0)

    @property
    def cache_read(self) -> int:
        return int(self.usage.get("cache_read_input_tokens", 0) or 0)

    @property
    def cache_creation(self) -> int:
        return int(self.usage.get("cache_creation_input_tokens", 0) or 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_creation

    def summary(self, label: str, halo_stats: dict | None) -> dict:
        return {
            "label": label,
            "halo_enabled": HALO_ENABLED,
            "halo_guidance_mode": HALO_GUIDANCE_MODE if HALO_ENABLED else None,
            "halo_threshold": HALO_THRESHOLD if HALO_ENABLED else None,
            "model": MODEL_VERSION,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cache_read": self.cache_read,
                "cache_creation": self.cache_creation,
                "total": self.total_tokens,
            },
            "total_cost_usd": self.cost_usd,
            "num_turns": self.num_turns,
            "tool_calls": dict(self.tool_calls),
            "halo": halo_stats,
            "is_error": self.is_error,
        }


def _render(message) -> None:
    """Best-effort pretty-printer for streamed SDK messages."""
    content = getattr(message, "content", None)
    if content is None:
        return
    for block in content:
        btype = type(block).__name__
        text = getattr(block, "text", None)
        if text:
            print(text, end="", flush=True)
        elif "ToolUse" in btype:
            name = getattr(block, "name", "?")
            print(f"\n  → tool call: {name} {getattr(block, 'input', '')}", flush=True)
        elif "ToolResult" in btype:
            print("\n  ← tool result received", flush=True)


def _halo_stats(session) -> dict | None:
    """Inspect the Halo session after the run: how many maps were encoded, store size."""
    if session is None:
        return None
    maps = getattr(session, "_maps", {})
    store = getattr(session, "store", None)
    try:
        nodes = len(store) if store is not None else None
    except TypeError:
        nodes = None
    return {"maps_encoded": len(maps), "map_ids": list(maps.keys()), "store_nodes": nodes}


async def run(request_id: str) -> None:
    from claude_agent_sdk import query

    options, session = build_options(HALO_ENABLED)
    meter = TokenMeter()

    prompt = (
        f"Process credit-line request {request_id}. Follow the full intake → "
        f"bureau → policy → score → decide → record → human-approval flow. "
        f"When you escalate, open the approval gate and wait for the credit "
        f"officer's resolution, then state the final outcome."
    )

    mode = f"HALO (threshold={HALO_THRESHOLD})" if HALO_ENABLED else "BASELINE (no Halo)"
    print(f"=== Credit-Line Decision Agent — request {request_id} — {mode} ===\n")
    async for message in query(prompt=prompt, options=options):
        _render(message)
        meter.observe(message)

    summary = meter.summary(RUN_LABEL, _halo_stats(session))

    runs_dir = PROJECT_ROOT / "runs"
    runs_dir.mkdir(exist_ok=True)
    out_path = runs_dir / f"{RUN_LABEL}.json"
    out_path.write_text(json.dumps(summary, indent=2))

    t = summary["tokens"]
    print("\n\n=== run complete ===")
    print("=== TOKENS ===")
    print(
        f"  label          : {summary['label']}  ({mode})\n"
        f"  input          : {t['input']:,}\n"
        f"  output         : {t['output']:,}\n"
        f"  cache_read     : {t['cache_read']:,}\n"
        f"  cache_creation : {t['cache_creation']:,}\n"
        f"  TOTAL tokens   : {t['total']:,}\n"
        f"  cost (usd)     : {summary['total_cost_usd']}\n"
        f"  turns          : {summary['num_turns']}\n"
        f"  tool calls     : {summary['tool_calls']}"
    )
    if summary["halo"]:
        print(f"  halo           : {summary['halo']}")
    print(f"  (written to {out_path.relative_to(PROJECT_ROOT)})")


if __name__ == "__main__":
    req = sys.argv[1] if len(sys.argv) > 1 else DEMO_REQUEST_ID
    asyncio.run(run(req))
