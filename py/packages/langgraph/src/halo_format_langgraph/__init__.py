"""halo_format_langgraph — Halo host adapter for LangChain agents and LangGraph graphs (Python).

The interception point is LangChain's ``wrap_tool_call`` — a deterministic wrap-the-tool-call hook, the
direct analog of the Claude Agent SDK's PostToolUse. Above a size threshold it encodes a tool result
into a shared store and rewrites the ToolMessage the model sees: ``content`` becomes a SHAPE MAP (not the
blob), and the full envelope rides in ``artifact`` (kept in graph state, never sent to the model). One
plain LangChain tool, ``halo_fetch(refs)``, backed by the same store, lets the model pull back the
withheld leaves (and expand branches), verified on read.

Two attach surfaces, one wrapper body:

  - ``install_halo(tools=..., middleware=...)`` — the primary path. Returns the augmented ``tools`` and
    ``middleware`` lists to splice into ``create_agent`` (plus the shared session). The Halo middleware
    is a ``HaloMiddleware`` (an ``AgentMiddleware`` subclass) providing both sync and async wrap.
  - ``halo_tool_node(tools=...)`` — for hand-built ``StateGraph``s. Returns a ``ToolNode`` with the same
    wrapper attached as ``wrap_tool_call`` / ``awrap_tool_call`` (plus the tools list and session).

MANDATORY correctness rule: the middleware must NOT re-encode the navigation tool's own output, or a
fetched leaf would be replaced by a new map and the model would never see the value. Enforced by an
``is_halo_nav_tool`` name check at the top of the wrapper.

Light vs. heavy (integration doc, Section 7): pass ``store=FileStore(dir)`` for cross-process
persistence, and wrap navigation with the L2 chain, without touching the control flow here."""

from typing import NamedTuple, Optional

from .accumulate import KeyOf, arg_join
from .constants import HALO_FETCH_TOOL, is_halo_nav_tool
from .middleware import (
    HaloMiddleware,
    make_async_wrapper,
    make_sync_wrapper,
)
from .nav_tool import create_halo_fetch_tool, halo_fetch
from .serialize import parse_tool_output, preview_of, serialize_envelope, shape_of, size_of
from .session import HaloSession


class InstallHaloResult(NamedTuple):
    tools: list  # your tools + halo_fetch, to pass to create_agent(tools=...)
    middleware: list  # your middleware + HaloMiddleware, to pass to create_agent(middleware=...)
    session: HaloSession  # the shared session (store + map registry), for audit swaps / inspection


class HaloToolNodeResult(NamedTuple):
    tool_node: object  # a langgraph ToolNode with the Halo wrapper attached
    tools: list  # your tools + halo_fetch, to bind to the model so it can call halo_fetch
    session: HaloSession


def _make_session(store, key_of, alg, now, session) -> HaloSession:
    return session if session is not None else HaloSession(
        store=store, key_of=key_of, alg=alg, now=now
    )


def install_halo(
    *,
    tools: Optional[list] = None,
    middleware: Optional[list] = None,
    threshold: int = 2048,
    store=None,
    key_of: Optional[KeyOf] = None,
    alg: str = "sha256",
    now=None,
    session: Optional[HaloSession] = None,
) -> InstallHaloResult:
    """Wire the Halo adapter into a ``create_agent`` setup. Append the returned ``tools`` and
    ``middleware`` to the call:

        result = install_halo(tools=my_tools)
        agent = create_agent(model, tools=result.tools, middleware=result.middleware)
    """
    session = _make_session(store, key_of, alg, now, session)
    mw = HaloMiddleware(session, threshold)
    fetch_tool = create_halo_fetch_tool(session)
    return InstallHaloResult(
        tools=[*(tools or []), fetch_tool],
        middleware=[*(middleware or []), mw],
        session=session,
    )


def halo_tool_node(
    tools: Optional[list] = None,
    *,
    threshold: int = 2048,
    store=None,
    key_of: Optional[KeyOf] = None,
    alg: str = "sha256",
    now=None,
    session: Optional[HaloSession] = None,
) -> HaloToolNodeResult:
    """Build a LangGraph ``ToolNode`` with the Halo wrapper attached, for hand-built ``StateGraph``s.

    Returns the node, the tools list (yours + ``halo_fetch``, to bind to the model), and the session.
    Import is deferred so that ``langgraph`` is only required for this path, not for ``install_halo``.
    """
    from langgraph.prebuilt import ToolNode

    session = _make_session(store, key_of, alg, now, session)
    fetch_tool = create_halo_fetch_tool(session)
    all_tools = [*(tools or []), fetch_tool]
    node = ToolNode(
        all_tools,
        wrap_tool_call=make_sync_wrapper(session, threshold),
        awrap_tool_call=make_async_wrapper(session, threshold),
    )
    return HaloToolNodeResult(tool_node=node, tools=all_tools, session=session)


__all__ = [
    "install_halo",
    "InstallHaloResult",
    "halo_tool_node",
    "HaloToolNodeResult",
    "HaloMiddleware",
    "make_sync_wrapper",
    "make_async_wrapper",
    "create_halo_fetch_tool",
    "halo_fetch",
    "HaloSession",
    "arg_join",
    "KeyOf",
    "size_of",
    "parse_tool_output",
    "serialize_envelope",
    "shape_of",
    "preview_of",
    "HALO_FETCH_TOOL",
    "is_halo_nav_tool",
]
