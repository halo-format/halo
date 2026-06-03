"""The navigation tools — how the model pulls back what the hook withheld. An in-process MCP server
exposing halo_walk and halo_fetch, both backed by the session store and verified on read.

halo_fetch takes a LIST of refs on purpose: each fetch is a separate model round trip, the dominant
latency in the loop, so the model is nudged to gather every ref a step needs and pull them in one
call. It returns a per-ref result, so one unknown or tampered entry (surfaced as a HashMismatch)
never sinks the batch.

The pure helpers (halo_walk / halo_fetch) are split from the MCP wrapping so they can be tested
without the SDK runtime; the tool() decorator is the only SDK-coupled surface."""

import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from .constants import HALO_FETCH_TOOL, HALO_MCP_SERVER, HALO_WALK_TOOL


def halo_walk(session, ref: str) -> dict:
    """Walk a branch ref to its summary and child handles; never returns leaf data."""
    return session.walk(ref)


def halo_fetch(session, refs) -> dict:
    """Fetch several leaf refs at once, verified, with a per-ref ok/error result."""
    return session.fetch(refs)


def _ok(value) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


def _fail(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _error_name(exc: Exception) -> str:
    name = type(exc).__name__
    return str(exc) if name == "RuntimeError" else name


_WALK_DESC = (
    "Expand a halo branch to its summary and child refs, without pulling any leaf data. "
    "Pass a ref like `m1.income` (or a raw `h:` handle). Use this to see a large branch's "
    "sub-structure before fetching deeper."
)

_FETCH_DESC = (
    "Fetch one or more halo leaves by ref, verified on read. Pass ALL the refs a step needs in one "
    "call (refs is a list) rather than one at a time — each call is a separate round trip. Returns "
    "a per-ref result; an entry with ok=false (e.g. HashMismatch) means that data must not be trusted."
)


def create_nav_server(session):
    """Build the in-process MCP server exposing halo_walk and halo_fetch over the given session."""

    @tool(HALO_WALK_TOOL, _WALK_DESC, {"ref": str})
    async def _walk(args):
        ref = args["ref"]
        try:
            return _ok(halo_walk(session, ref))
        except Exception as exc:  # surface a navigation error as tool output, not a crash
            return _fail(f'halo_walk failed for "{ref}": {_error_name(exc)}')

    @tool(HALO_FETCH_TOOL, _FETCH_DESC, {"refs": list[str]})
    async def _fetch(args):
        return _ok(halo_fetch(session, args["refs"]))

    return create_sdk_mcp_server(HALO_MCP_SERVER, tools=[_walk, _fetch])
