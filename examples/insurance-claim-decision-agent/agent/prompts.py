"""Agent identity and model/prompt provenance.

CLAUDE.md is the single source of truth for the agent's operating instructions —
it governs both the Claude Code CLI runtime and the Agent SDK runtime. So the
canonical ``PROMPT_VERSION_HASH`` is a sha256 over CLAUDE.md's raw bytes, and
that exact value is what every runtime records via ``payer_record_decision`` so a
recorded decision pins precisely which prompt produced it.

The MCP server exposes the same value through ``payer_get_agent_provenance`` so a
CLI agent that never imports this module still records the canonical hash.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

AGENT_ID = "insurance-claim-decision-agent"
AGENT_VERSION = "0.1.0"
MODEL_VERSION = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")

_CLAUDE_MD = Path(__file__).resolve().parent.parent / "CLAUDE.md"

_FALLBACK_PROMPT = (
    "You are the Insurance Claim Decision Agent. Act only through the mimic-payer "
    "MCP tools. The model orchestrates and reasons; the deterministic engine computes "
    "the money; a human owns every denial, reduction, or pend."
)


def _load_prompt() -> bytes:
    try:
        return _CLAUDE_MD.read_bytes()
    except OSError:
        return _FALLBACK_PROMPT.encode("utf-8")


_PROMPT_BYTES = _load_prompt()

# The SDK system prompt IS the CLAUDE.md content, so both runtimes are governed by
# — and pin the hash of — the same instructions.
SYSTEM_PROMPT = _PROMPT_BYTES.decode("utf-8")
PROMPT_VERSION_HASH = "sha256:" + hashlib.sha256(_PROMPT_BYTES).hexdigest()
