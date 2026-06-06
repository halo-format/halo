"""Anthropic prompt caching for the LangGraph agent (`CACHE=1`).

`ChatAnthropic` does not cache by default, so every model turn re-sends the whole
conversation as fresh input. This middleware sets moving **cache breakpoints**
(`cache_control: ephemeral`) on the system prompt and on the latest message before each
model call. Anthropic then caches the growing conversation prefix once (a cache *write*,
~1.25x) and re-reads it on later turns at ~0.1x instead of full price.

It applies to whichever agent it's added to, so the A/B stays fair: run baseline and Halo
both with `CACHE=1`. Caching mostly changes *long* loops (where a big tool result is
re-read many turns); a one-shot fetch sees little benefit because nothing re-reads it.
"""
from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

_EPHEMERAL = {"type": "ephemeral"}


def _with_breakpoint(msg):
    """Return a copy of msg with a cache_control breakpoint on its last content block."""
    content = msg.content
    if isinstance(content, str):
        if not content:
            return msg
        blocks = [{"type": "text", "text": content, "cache_control": _EPHEMERAL}]
    elif isinstance(content, list) and content:
        blocks = [dict(b) if isinstance(b, dict) else {"type": "text", "text": str(b)} for b in content]
        blocks[-1] = {**blocks[-1], "cache_control": _EPHEMERAL}
    else:
        return msg
    return msg.model_copy(update={"content": blocks})


class PromptCachingMiddleware(AgentMiddleware):
    """Set a moving Anthropic cache breakpoint on the system prompt + the latest message."""

    def _apply(self, request):
        overrides = {}
        if request.system_message is not None:
            overrides["system_message"] = _with_breakpoint(request.system_message)
        if request.messages:
            overrides["messages"] = [*request.messages[:-1], _with_breakpoint(request.messages[-1])]
        return request.override(**overrides) if overrides else request

    def wrap_model_call(self, request, handler):
        return handler(self._apply(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._apply(request))
