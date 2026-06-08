"""Agent identity + model/prompt provenance. CLAUDE.md is the operating manual
(shared verbatim with the other ports), so the canonical PROMPT_VERSION_HASH is a
sha256 over its bytes — byte-identical across every runtime."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

AGENT_ID = "insurance-claim-decision-agent"
# This port runs on the OpenAI Agents SDK, natively against an OpenAI model.
MODEL_VERSION = os.environ.get("AGENT_MODEL", "gpt-4.1")
_CLAUDE_MD = Path(__file__).resolve().parent.parent / "CLAUDE.md"

try:
    _BYTES = _CLAUDE_MD.read_bytes()
except OSError:
    _BYTES = b"You are the Insurance Claim Decision Agent."

SYSTEM_PROMPT = _BYTES.decode("utf-8")
PROMPT_VERSION_HASH = "sha256:" + hashlib.sha256(_BYTES).hexdigest()
