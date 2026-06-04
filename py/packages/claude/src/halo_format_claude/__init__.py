"""halo_format_claude — Halo host adapter for the Claude Agent SDK (Python).

install_halo(options, ...) augments the SDK options with:
  - a PostToolUse encode hook that, above a size threshold, encodes a tool result into a shared
    store and sets updatedToolOutput to the envelope (the map), not the blob;
  - an in-process MCP server exposing ONE tool, halo_fetch(refs), backed by the same store, for the
    model to pull back the withheld leaves (and expand branches), verified on read.

One call to adopt the adapter. Plumbing (the hook) is deterministic and fires always; the Skill
(loaded separately by the host) is guidance that shapes how the model navigates. The two stay
separate on purpose: a weak Skill costs some efficiency but never the core property — the payload is
out of context regardless.

MANDATORY correctness rule: the hook must NOT re-encode the halo navigation tools' own output, or a
fetched leaf would be replaced by a new map and the model would never see the value. This is enforced
two ways: the matcher below excludes them by name, and the hook guards on tool name.

Light vs. heavy (SDK integration, Section 7): pass ``store=FileStore(dir)`` for cross-session
persistence, and wrap navigation with the L2 chain, without touching the control flow here."""

from dataclasses import replace
from typing import NamedTuple, Optional

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from .accumulate import KeyOf, arg_join
from .constants import (
    HALO_FETCH_TOOL,
    HALO_MCP_SERVER,
    HALO_TOOL_PREFIX,
    is_halo_nav_tool,
)
from .encode_hook import create_encode_hook
from .nav_tools import create_nav_server, halo_fetch
from .serialize import parse_tool_output, preview_of, serialize_envelope, shape_of, size_of
from .session import HaloSession

# Matches every tool name EXCEPT the halo navigation tools, so the encode hook skips them. The
# in-hook guard is the load-bearing exclusion; this matcher is the belt to its suspenders.
NOT_HALO_TOOLS = f"^(?!{HALO_TOOL_PREFIX})"


class InstallHaloResult(NamedTuple):
    options: ClaudeAgentOptions  # the augmented SDK options to pass to query()
    session: HaloSession  # the shared session (store + map registry), for audit swaps / inspection


def install_halo(
    options: Optional[ClaudeAgentOptions] = None,
    *,
    threshold: int = 2048,
    store=None,
    key_of: Optional[KeyOf] = None,
    alg: str = "sha256",
    now=None,
    session: Optional[HaloSession] = None,
) -> InstallHaloResult:
    """Wire the Halo adapter into a set of SDK options. Returns the augmented options and session."""
    options = options if options is not None else ClaudeAgentOptions()
    session = session if session is not None else HaloSession(
        store=store, key_of=key_of, alg=alg, now=now
    )
    encode_hook = create_encode_hook(session, threshold)

    # The matcher scopes this to PostToolUse, so input is always a PostToolUse event at runtime.
    async def callback(input_data, tool_use_id, context):
        if input_data.get("hook_event_name") != "PostToolUse":
            return {}
        return await encode_hook(input_data, tool_use_id, context)

    matcher = HookMatcher(matcher=NOT_HALO_TOOLS, hooks=[callback])
    hooks = dict(options.hooks or {})
    hooks["PostToolUse"] = [*hooks.get("PostToolUse", []), matcher]

    if isinstance(options.mcp_servers, dict):
        servers = dict(options.mcp_servers)
    elif not options.mcp_servers:
        servers = {}
    else:
        raise ValueError(
            "install_halo needs mcp_servers to be a dict to add the in-process halo server; "
            "got a str/Path config. Merge the halo server into a dict mcp_servers instead."
        )
    servers[HALO_MCP_SERVER] = create_nav_server(session)

    augmented = replace(options, hooks=hooks, mcp_servers=servers)
    return InstallHaloResult(options=augmented, session=session)


__all__ = [
    "install_halo",
    "InstallHaloResult",
    "HaloSession",
    "create_encode_hook",
    "create_nav_server",
    "halo_fetch",
    "arg_join",
    "KeyOf",
    "size_of",
    "parse_tool_output",
    "serialize_envelope",
    "shape_of",
    "preview_of",
    "HALO_MCP_SERVER",
    "HALO_FETCH_TOOL",
    "HALO_TOOL_PREFIX",
    "is_halo_nav_tool",
    "NOT_HALO_TOOLS",
]
