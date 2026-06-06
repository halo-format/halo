"""The navigation surface — how the model pulls back what the hook withheld. An in-process MCP server
exposing exactly ONE tool, halo_fetch, backed by the session store and verified on read.

One tool on purpose: an earlier version also exposed halo_walk (expand a branch) alongside halo_fetch
(pull leaves), and the model wasted turns choosing between them and fetching a branch ref through the
leaf tool. halo_fetch now does both — a leaf ref returns its value, a branch ref returns its sub-shape
— so there is a single batch API and nothing to disambiguate.

halo_fetch takes a LIST of refs: each fetch is a separate model round trip, the dominant latency in
the loop, so the model is nudged to gather every ref a step needs and pull them in one call. It
returns a per-ref result, so one unknown or tampered entry (surfaced as a HashMismatch) never sinks
the batch.

The pure helper (halo_fetch) is split from the MCP wrapping so it can be tested without the SDK
runtime; the tool() decorator is the only SDK-coupled surface."""

import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from .constants import HALO_FETCH_DESCRIPTION, HALO_FETCH_TOOL, HALO_MCP_SERVER


def halo_fetch(session, refs) -> dict:
    """Fetch several refs at once, verified, with a per-ref result; branch refs return their sub-shape."""
    return session.fetch(refs)


def _ok(value) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


def create_nav_server(session):
    """Build the in-process MCP server exposing the single halo_fetch tool over the given session."""

    @tool(HALO_FETCH_TOOL, HALO_FETCH_DESCRIPTION, {"refs": list[str]})
    async def _fetch(args):
        return _ok(halo_fetch(session, args["refs"]))

    return create_sdk_mcp_server(HALO_MCP_SERVER, tools=[_fetch])
