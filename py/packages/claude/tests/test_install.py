import asyncio
import json

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

from halo_format_claude import install_halo
from halo_format_claude.constants import HALO_MCP_SERVER, HALO_TOOL_PREFIX


def test_wiring_adds_hook_and_server_preserving_existing_config():
    existing = HookMatcher(matcher="Bash", hooks=[])
    base = ClaudeAgentOptions(
        hooks={"PostToolUse": [existing], "PreToolUse": [existing]},
        mcp_servers={"other": {"type": "sdk", "name": "other", "instance": None}},
    )

    options, _session = install_halo(base)

    post = options.hooks["PostToolUse"]
    assert len(post) == 2
    assert post[0] is existing
    assert post[1].matcher == f"^(?!{HALO_TOOL_PREFIX})"

    assert options.hooks["PreToolUse"] == [existing]
    assert "other" in options.mcp_servers
    assert HALO_MCP_SERVER in options.mcp_servers


def test_end_to_end_hook_encodes_and_session_navigates():
    options, session = install_halo(ClaudeAgentOptions(), now=lambda: "T")
    callback = options.hooks["PostToolUse"][-1].hooks[0]

    payload = json.dumps(
        {"profile": {"income": {"monthly": 4200}, "debts": {"monthly": 2604}}, "filler": "x" * 2000}
    )
    input_data = {
        "hook_event_name": "PostToolUse",
        "tool_name": "bureau_report",
        "tool_input": {"applicant": 99},
        "tool_response": payload,
        "tool_use_id": "u1",
    }

    out = asyncio.run(callback(input_data, "u1", {}))
    assert "hookSpecificOutput" in out

    got = session.fetch(["99.bureau_report.profile"])
    assert got["99.bureau_report.profile"] == {
        "ok": True,
        "value": {"income": {"monthly": 4200}, "debts": {"monthly": 2604}},
    }
