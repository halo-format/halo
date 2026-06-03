import asyncio
import json

from halo_format_claude.constants import HALO_FETCH_TOOL, HALO_TOOL_PREFIX
from halo_format_claude.encode_hook import create_encode_hook
from halo_format_claude.session import HaloSession


def hook_input(tool_name, tool_response, tool_input=None):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": {} if tool_input is None else tool_input,
        "tool_response": tool_response,
        "tool_use_id": "u1",
    }


BIG_RESULT = json.dumps({"rows": [{"i": i, "v": f"row-{i}-{'x' * 40}"} for i in range(80)]})


def test_replaces_large_result_with_the_envelope():
    s = HaloSession(now=lambda: "T")
    hook = create_encode_hook(s, threshold=2048)
    out = asyncio.run(hook(hook_input("query_db", BIG_RESULT), "u1", {}))

    so = out["hookSpecificOutput"]
    assert so["hookEventName"] == "PostToolUse"
    assert isinstance(so["updatedToolOutput"], str)
    assert "[halo]" in so["updatedToolOutput"]

    envelope = json.loads(so["updatedToolOutput"].split("\n", 1)[1])
    assert envelope["halo"] == "1"
    assert envelope["source"]["id"] == "m1"
    assert envelope["source"]["tool"] == "query_db"


def test_small_result_passes_through_untouched():
    s = HaloSession()
    hook = create_encode_hook(s, threshold=2048)
    assert asyncio.run(hook(hook_input("ping", '{"ok":true}'), "u1", {})) == {}


def test_mandatory_never_reencodes_nav_tool_output():
    s = HaloSession()
    hook = create_encode_hook(s, threshold=2048)
    out = asyncio.run(hook(hook_input(f"{HALO_TOOL_PREFIX}{HALO_FETCH_TOOL}", BIG_RESULT), "u1", {}))
    assert out == {}
    # And nothing was ingested: a fresh fetch finds no map.
    assert s.fetch(["m1.x"]) == {"m1.x": {"ok": False, "error": "UnknownHandle"}}
