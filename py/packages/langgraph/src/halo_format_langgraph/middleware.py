"""The encode middleware — the plumbing. It wraps every tool call: it runs the tool via the handler,
and above a size threshold rewrites the resulting ToolMessage so the model sees a SHAPE MAP instead of
the blob, while the full payload goes to the store and the full envelope rides in ``ToolMessage.artifact``
(kept in graph state, never serialized into the model's context). This is deterministic and
model-independent: the payload is out of context before the model is involved, so the model cannot leak
a full result by forgetting to navigate.

The same wrapper body drives two LangChain/LangGraph surfaces, which share one ``ToolCallWrapper`` shape
``(request, handler/execute) -> ToolMessage | Command``:

  - ``create_agent(middleware=[...])`` — via the ``HaloMiddleware`` subclass below (the primary path);
  - ``ToolNode(wrap_tool_call=..., awrap_tool_call=...)`` — via the bare functions, for hand-built graphs.

Two passthrough conditions, in order (mirrors the Claude encode hook):
  1. The tool IS the halo navigation tool. MANDATORY: re-encoding a fetched leaf would replace it with
     a new map and the model would never receive the value.
  2. The ToolMessage content is below the size threshold, or is not JSON-ish — pass through untouched.

A non-``ToolMessage`` return (a ``Command`` that updates graph state directly) always passes through:
there is nothing to encode.

The session underneath is SYNC (port convention); only the async surface awaits the handler."""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from .constants import is_halo_nav_tool
from .serialize import parse_tool_output, serialize_envelope, size_of

_DEFAULT_THRESHOLD = 2048

# Where an upstream tool's own artifact is preserved if Halo needs the slot for its envelope, so a
# tool that already used content_and_artifact does not silently lose its data.
_PRIOR_ARTIFACT_KEY = "halo_prior_artifact"


def _rewrite(session, threshold: int, msg, request):
    """Encode a tool's ToolMessage and return a rewritten copy: content -> shape map, artifact ->
    envelope. Returns the message untouched when it should pass through. Builds a copy via
    ``model_copy`` rather than mutating in place, so a handler that returns a shared/cached message is
    never clobbered (the safe path — the handler's tool_call_id, name and status are preserved)."""
    if not isinstance(msg, ToolMessage):
        return msg  # a Command (state update) or other return — nothing to encode
    if size_of(msg.content) < threshold:
        return msg
    value = parse_tool_output(msg.content)
    if value is None:
        return msg

    tool_call = request.tool_call
    result = session.ingest(tool_call["name"], tool_call.get("args"), value)
    hints = session.describe(result["envelope"])

    update = {
        "content": serialize_envelope(result["envelope"], hints),  # the SHAPE MAP (model-visible)
        "artifact": result["envelope"],  # full envelope (out of context, persisted in state)
    }
    if msg.artifact is not None:
        # Preserve an upstream content_and_artifact tool's own artifact rather than dropping it.
        update["additional_kwargs"] = {
            **(msg.additional_kwargs or {}),
            _PRIOR_ARTIFACT_KEY: msg.artifact,
        }
    return msg.model_copy(update=update)


def make_sync_wrapper(session, threshold: int = _DEFAULT_THRESHOLD):
    """The sync ToolCallWrapper for ToolNode(wrap_tool_call=...) and the middleware's sync path."""

    def wrapper(request, handler):
        if is_halo_nav_tool(request.tool_call["name"]):
            return handler(request)  # MANDATORY: never re-encode a fetched leaf
        return _rewrite(session, threshold, handler(request), request)

    return wrapper


def make_async_wrapper(session, threshold: int = _DEFAULT_THRESHOLD):
    """The async ToolCallWrapper for ToolNode(awrap_tool_call=...) and the middleware's async path."""

    async def wrapper(request, handler):
        if is_halo_nav_tool(request.tool_call["name"]):
            return await handler(request)
        return _rewrite(session, threshold, await handler(request), request)

    return wrapper


class HaloMiddleware(AgentMiddleware):
    """The create_agent middleware. Provides both ``wrap_tool_call`` and ``awrap_tool_call`` over one
    shared wrapper body, so the adapter works under both ``agent.invoke`` and ``agent.ainvoke``."""

    def __init__(self, session, threshold: int = _DEFAULT_THRESHOLD):
        super().__init__()
        self._sync = make_sync_wrapper(session, threshold)
        self._async = make_async_wrapper(session, threshold)

    def wrap_tool_call(self, request, handler):
        return self._sync(request, handler)

    async def awrap_tool_call(self, request, handler):
        return await self._async(request, handler)
