"""The encode middleware: the wrapper rewrites a large ToolMessage into a shape map (content) plus the
envelope (artifact), and passes through everything it must — the nav tool, small results, and non-
ToolMessage returns (a Command). Sync and async share one body, so both are exercised."""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from halo_format_langgraph import HaloMiddleware, HaloSession
from halo_format_langgraph.middleware import _PRIOR_ARTIFACT_KEY

BIG = '{"profile":{"income":{"monthly":4200},"debts":{"monthly":2604}},"filler":"' + "x" * 3000 + '"}'


def _req(name, args):
    # The wrapper only reads request.tool_call; a namespace is enough for the unit level.
    return SimpleNamespace(tool_call={"name": name, "args": args, "id": "c1"})


def _handler(content, artifact=None):
    def handler(request):
        return ToolMessage(
            content=content, tool_call_id="c1", name=request.tool_call["name"], artifact=artifact
        )

    return handler


def _mw():
    session = HaloSession(now=lambda: "T")
    return HaloMiddleware(session, threshold=2048), session


def test_large_result_becomes_shape_map_with_envelope_artifact():
    mw, session = _mw()
    out = mw.wrap_tool_call(_req("bureau", {"applicant": 99}), _handler(BIG))

    assert out.content.startswith('[halo] map "99"')  # arg_join keyed on applicant=99
    assert out.artifact["halo"] == "1"
    assert out.artifact["source"]["id"] == "99"
    # the full payload is reachable from the store, not in content
    assert session.fetch(["99.profile"])["99.profile"]["ok"] is True


def test_async_path_matches_sync():
    session = HaloSession(now=lambda: "T")
    mw = HaloMiddleware(session, 2048)

    async def handler(request):
        return ToolMessage(content=BIG, tool_call_id="c1", name=request.tool_call["name"])

    out = asyncio.run(mw.awrap_tool_call(_req("bureau", {"applicant": 99}), handler))
    assert out.content.startswith('[halo] map "99"')
    assert out.artifact["halo"] == "1"


def test_nav_tool_output_passes_through_untouched():
    # MANDATORY: a fetched leaf must never be re-encoded into a new map.
    mw, _ = _mw()
    out = mw.wrap_tool_call(_req("halo_fetch", {"refs": ["x"]}), _handler(BIG))
    assert out.content == BIG
    assert out.artifact is None


def test_small_result_passes_through():
    mw, _ = _mw()
    out = mw.wrap_tool_call(_req("ping", {"x": 1}), _handler('{"ok":true}'))
    assert out.content == '{"ok":true}'
    assert out.artifact is None


def test_command_return_passes_through():
    mw, _ = _mw()

    def handler(request):
        return Command(update={"foo": "bar"})

    out = mw.wrap_tool_call(_req("set_state", {"a": 1}), handler)
    assert isinstance(out, Command)


def test_upstream_artifact_is_preserved():
    mw, _ = _mw()
    out = mw.wrap_tool_call(_req("with_art", {"a": 7}), _handler(BIG, artifact={"mine": 1}))
    assert out.artifact["halo"] == "1"  # Halo's envelope takes the artifact slot
    assert out.additional_kwargs[_PRIOR_ARTIFACT_KEY] == {"mine": 1}  # upstream artifact kept


def test_original_message_not_mutated():
    # _rewrite returns a copy; the handler's message object is left intact.
    mw, _ = _mw()
    original = ToolMessage(content=BIG, tool_call_id="c1", name="bureau")

    def handler(request):
        return original

    out = mw.wrap_tool_call(_req("bureau", {"applicant": 99}), handler)
    assert out is not original
    assert original.content == BIG  # untouched
