"""Live Insurance Claim Decision Agent on the Claude Agent SDK.

Registers the `mimic-payer` MCP server as an external stdio subprocess, loads the
project Skills (intake-and-validate / coverage-and-rules / adjudicate /
explain-decision), and adjudicates one claim end to end — including blocking on
the human review gate when any line denies, reduces, or pends, or the claim is
above the auto-finalize ceiling.

    python -m agent.main [CLAIM_ID]

Token accounting is always on: every run prints a TOKENS summary and writes it to
``runs/<label>.json``.

Set ``HALO=1`` to route every tool result through the Halo adapter
(``halo_format_claude.install_halo``): large results (the claim with its clinical
attachments, the claim history, the whole-plan benefit rules) are encoded into a
content-addressed map that stays out of the model's context — the model sees a
shape map — and the agent pulls back only the fields it needs via ``halo_fetch``,
verified on read. Run with and without it to compare token usage.

Requires a seeded mimic_payer database. Resolve any pending review from a second
terminal with scripts/reviewer_console.py.
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

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_CLAIM_ID = "CLM-1001"

HALO_ENABLED = os.environ.get("HALO", "").lower() in ("1", "true", "yes", "on")
HALO_THRESHOLD = int(os.environ.get("HALO_THRESHOLD", "2048"))
HALO_GUIDANCE_MODE = os.environ.get("HALO_GUIDANCE_MODE", "skill").lower()
RUN_LABEL = os.environ.get("RUN_LABEL", "halo" if HALO_ENABLED else "baseline")

MCP_TOOLS = [
    "mcp__mimic-payer__payer_get_agent_provenance",
    "mcp__mimic-payer__payer_get_claim",
    "mcp__mimic-payer__payer_get_member_coverage",
    "mcp__mimic-payer__payer_get_benefit_rules",
    "mcp__mimic-payer__payer_get_accumulators",
    "mcp__mimic-payer__payer_get_claim_history",
    "mcp__mimic-payer__payer_check_network",
    "mcp__mimic-payer__payer_get_allowed_amount",
    "mcp__mimic-payer__payer_lookup_reason_code",
    "mcp__mimic-payer__payer_adjudicate_line",
    "mcp__mimic-payer__payer_record_decision",
    "mcp__mimic-payer__payer_request_review",
    "mcp__mimic-payer__payer_post_adjudication",
]

# One navigation tool only — the adapter exposes a single halo_fetch.
HALO_TOOLS = ["mcp__halo__halo_fetch"]

# Project Skills. The halo-navigation skill is enabled ONLY for the Halo run (and
# only in "skill" guidance mode); the encode hook is the plumbing, the Skill is the
# guidance.
BASE_SKILLS = ["intake-and-validate", "coverage-and-rules", "adjudicate", "explain-decision"]

# Same navigation guidance as the halo-navigation Skill, for "prompt" mode.
HALO_GUIDANCE = """

## Halo: navigating large tool results

Some tool results come back not as the full payload but as a *halo shape map* — a `[halo] map "<id>"
— <root kind> …` note followed by one line per field giving its ref, kind, and a bounded preview; the
data is held, verified, in a store out of your context. When you receive one: read the previews
(they often answer the step in place), then fetch ONLY the fields you still need in a single
`mcp__halo__halo_fetch` call, passing a list of refs like `["<mapId>.lines", ...]` (batch them; each
value is verified). A `[branch]` ref is not a value — `halo_fetch` it to get its sub-refs, then fetch
the leaf. For a claim, fetch the service `lines` (codes, amounts, tooth/surface) and skip the
`attachment_bodies` bulk unless a line needs clinical review. For claim history, fetch only the codes
relevant to a frequency or duplicate check. Use fetched values as if returned inline.
"""


def build_options(halo: bool):
    """Return (options, session). session is the HaloSession when halo is on, else None."""
    from claude_agent_sdk import ClaudeAgentOptions

    mcp_env = {
        "MIMIC_DB_DSN": os.environ["MIMIC_DB_DSN"],
        "APPROVAL_TIMEOUT_SECONDS": os.environ.get("APPROVAL_TIMEOUT_SECONDS", "900"),
        "APPROVAL_POLL_SECONDS": os.environ.get("APPROVAL_POLL_SECONDS", "2"),
        "AUTO_FINALIZE_MAX_CENTS": os.environ.get("AUTO_FINALIZE_MAX_CENTS", "50000"),
        "PATH": os.environ.get("PATH", ""),
    }

    use_skill = halo and HALO_GUIDANCE_MODE == "skill"
    use_prompt = halo and HALO_GUIDANCE_MODE == "prompt"

    options = ClaudeAgentOptions(
        model=MODEL_VERSION,
        system_prompt=SYSTEM_PROMPT + (HALO_GUIDANCE if use_prompt else ""),
        cwd=str(PROJECT_ROOT),
        setting_sources=["project"],
        skills=BASE_SKILLS + (["halo-navigation"] if use_skill else []),
        allowed_tools=MCP_TOOLS + (HALO_TOOLS if halo else []),
        thinking={"type": "adaptive", "display": "summarized"},
        # bypassPermissions is the convenient default for an unattended example; the
        # project's .claude/settings.json already allow-lists every tool, so set
        # AGENT_PERMISSION_MODE=default in environments where bypass is disallowed
        # (e.g. running as root) and the allow-list still auto-approves the tools.
        permission_mode=os.environ.get("AGENT_PERMISSION_MODE", "bypassPermissions"),
        mcp_servers={
            "mimic-payer": {
                "command": sys.executable,
                "args": ["-m", "mcp_servers.mimic_payer.server"],
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
    if session is None:
        return None
    maps = getattr(session, "_maps", {})
    store = getattr(session, "store", None)
    try:
        nodes = len(store) if store is not None else None
    except TypeError:
        nodes = None
    return {"maps_encoded": len(maps), "map_ids": list(maps.keys()), "store_nodes": nodes}


async def run(claim_id: str) -> None:
    from claude_agent_sdk import query

    options, session = build_options(HALO_ENABLED)
    meter = TokenMeter()

    prompt = (
        f"Adjudicate insurance claim {claim_id}. Follow the full intake-and-validate "
        f"→ coverage-and-rules → adjudicate → explain flow, deciding each service line "
        f"(pay / deny / reduce / pend) with the deterministic engine and the standard "
        f"reason codes. Record the decisions with evidence. If any line denies, reduces, "
        f"or pends — or the claim is above the auto-finalize ceiling — open the human "
        f"review gate, wait for the examiner, then post the adjudication and give the "
        f"EOB-style explanation."
    )

    mode = f"HALO (threshold={HALO_THRESHOLD})" if HALO_ENABLED else "BASELINE (no Halo)"
    print(f"=== Insurance Claim Decision Agent — claim {claim_id} — {mode} ===\n")
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
    cid = sys.argv[1] if len(sys.argv) > 1 else DEMO_CLAIM_ID
    asyncio.run(run(cid))
