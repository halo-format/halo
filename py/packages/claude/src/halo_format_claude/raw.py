"""halo_format_claude.raw — the Halo adapter for the RAW Claude Messages API.

The Agent SDK adapter (``install_halo``, the package root) leans on a PostToolUse hook to encode every
tool result before the model sees it. The raw Messages API has no hook: you own the tool-use loop on
``anthropic.Anthropic().messages.create(...)``. This module gives you the same mechanism to drive by
hand — encode a large result into the session store, hand the model a shape map, and expose a
``halo_fetch`` tool to pull back the verified leaves.

This is the runtime where Halo's token win is largest: the raw API re-sends every tool result in
context on each turn (no host scratch-spill) and the cached prefix is small, so keeping a heavy
payload out of context is bytes the baseline would otherwise resend every turn.

This module imports ZERO Agent SDK code — only the SDK-free core of the adapter (HaloSession, the
serializer, the accumulation policy). With the package's lazy ``__init__``, a raw-Messages-API app can
``import halo_format_claude.raw`` without installing ``claude-agent-sdk`` at all.
"""

import json
from typing import Callable, Optional

from .accumulate import KeyOf, arg_join
from .constants import HALO_FETCH_DESCRIPTION, HALO_FETCH_TOOL
from .serialize import parse_tool_output, serialize_envelope, size_of
from .session import HaloSession

_DEFAULT_THRESHOLD = 2048


def halo_fetch_tool_def() -> dict:
    """The halo_fetch tool definition in raw Messages API shape — add it to your ``tools`` list."""
    return {
        "name": HALO_FETCH_TOOL,
        "description": HALO_FETCH_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The halo refs to fetch together in one call.",
                }
            },
            "required": ["refs"],
        },
    }


# Navigation guidance to append to your system prompt. The hook-based adapter delivers this via a
# Skill; on the raw API you put it in the prompt yourself. It is intentionally generic — append a
# one-line domain hint (e.g. "fetch the line items, not the attachment bodies") if it helps.
HALO_GUIDANCE = """
## Halo: navigating large tool results

Some tool results come back not as the full payload but as a *halo shape map* — a `[halo] map "<id>"`
note with one line per field giving its ref, kind, and a bounded preview; the full data is held,
verified, in a store outside your context. Read the previews first and answer from them when you can.
For anything a preview does not settle, fetch ONLY the fields you still need in a SINGLE halo_fetch
call, passing every ref as a list (e.g. ["m1.lines", "m1.total"]). A [branch] ref expands to its
sub-refs; every other ref returns its value. Each value is verified on read — an entry with ok=false
(e.g. HashMismatch) must not be trusted. Use fetched values as if returned inline; never fetch fields
you do not need.
"""


class RawHalo:
    """The raw Messages API adapter: a session plus the helpers a manual tool-use loop needs.

    Add ``tool_def`` to your ``tools`` and ``guidance`` to your system prompt, then in your dispatch
    route a ``halo_fetch`` call (see ``is_fetch``) to ``fetch(refs)`` and every other tool result to
    ``encode_result(name, args, value)``.
    """

    def __init__(
        self,
        *,
        threshold: int = _DEFAULT_THRESHOLD,
        store=None,
        key_of: Optional[KeyOf] = None,
        alg: str = "sha256",
        now: Optional[Callable[[], str]] = None,
        session: Optional[HaloSession] = None,
    ):
        self.threshold = threshold
        self.session = session if session is not None else HaloSession(
            store=store, key_of=key_of or arg_join, alg=alg, now=now
        )
        #: The halo_fetch tool definition to add to your ``tools`` list.
        self.tool_def = halo_fetch_tool_def()
        #: Navigation guidance to append to your system prompt.
        self.guidance = HALO_GUIDANCE

    def is_fetch(self, tool_name: str) -> bool:
        """True if a tool-use block names halo_fetch (route it to ``fetch``, never re-encode it).

        The raw API tool is the bare ``halo_fetch`` name, with none of the ``mcp__halo__`` prefix the
        in-process MCP server adds on the Agent SDK path.
        """
        return tool_name == HALO_FETCH_TOOL

    def fetch(self, refs) -> str:
        """Answer a halo_fetch call: verified per-ref results as the JSON string for tool_result content."""
        # MANDATORY: this is the only place a fetched leaf is returned — never re-encode it, or the
        # model would receive another map instead of the value.
        return json.dumps(self.session.fetch(refs))

    def encode_result(self, tool_name: str, tool_input, value) -> str:
        """Process a domain tool's result for the model.

        Above the size threshold it is encoded into the store and a shape map string is returned in
        its place; below it the raw JSON payload passes through. Either way the return value is the
        string to put in the tool_result content.
        """
        if size_of(value) < self.threshold:
            return json.dumps(value)
        result = self.session.ingest(tool_name, tool_input, value)
        hints = self.session.describe(result["envelope"])
        return serialize_envelope(result["envelope"], hints)


def create_raw_halo(
    *,
    threshold: int = _DEFAULT_THRESHOLD,
    store=None,
    key_of: Optional[KeyOf] = None,
    alg: str = "sha256",
    now: Optional[Callable[[], str]] = None,
    session: Optional[HaloSession] = None,
) -> RawHalo:
    """Wire the Halo raw-Messages-API adapter. Returns a :class:`RawHalo` bundle for the manual loop."""
    return RawHalo(
        threshold=threshold, store=store, key_of=key_of, alg=alg, now=now, session=session
    )


__all__ = [
    "RawHalo",
    "create_raw_halo",
    "halo_fetch_tool_def",
    "HALO_GUIDANCE",
    "HaloSession",
    "arg_join",
    "KeyOf",
    "parse_tool_output",
    "serialize_envelope",
    "size_of",
    "HALO_FETCH_TOOL",
    "HALO_FETCH_DESCRIPTION",
]
