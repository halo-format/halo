"""The navigation tool: a single LangChain tool, halo_fetch, declared content_and_artifact. A leaf ref
returns its value; a branch ref returns its sub-shape rather than erroring; the per-ref result rides in
both content (read by the model) and artifact (kept in state)."""

import json

from halo_format_langgraph import HaloSession, create_halo_fetch_tool
from halo_format_langgraph.constants import HALO_FETCH_TOOL
from halo_format_langgraph.nav_tool import halo_fetch


def _seed():
    # Large enough (> the core's 1024-byte inline threshold) that the top-level object carves into
    # branches: a scalar leaf (score) and a chunked-array branch (tradelines).
    session = HaloSession(now=lambda: "T")
    session.ingest(
        "bureau",
        {"applicant": 99},
        {
            "score": 612,
            "tradelines": [
                {"id": i, "creditor": f"Bank {i}", "balance": i * 137, "status": "open"}
                for i in range(40)
            ],
        },
    )
    return session


def test_helper_fetches_leaf_verified():
    session = _seed()
    got = halo_fetch(session, ["99.score"])
    assert got["99.score"] == {"ok": True, "value": 612}


def test_helper_branch_ref_returns_sub_shape():
    session = _seed()
    got = halo_fetch(session, ["99.tradelines"])
    assert got["99.tradelines"]["ok"] is True
    assert got["99.tradelines"]["kind"] == "branch"
    assert any(f["ref"] == "99.tradelines.0" for f in got["99.tradelines"]["fields"])


def test_tool_is_named_and_content_and_artifact():
    session = _seed()
    tool = create_halo_fetch_tool(session)
    assert tool.name == HALO_FETCH_TOOL
    assert tool.response_format == "content_and_artifact"


def test_tool_invocation_returns_content_and_artifact():
    session = _seed()
    tool = create_halo_fetch_tool(session)
    msg = tool.invoke(
        {"type": "tool_call", "name": HALO_FETCH_TOOL, "args": {"refs": ["99.score"]}, "id": "c1"}
    )
    # content is the JSON the model reads; artifact is the same structured result kept in state.
    assert json.loads(msg.content)["99.score"] == {"ok": True, "value": 612}
    assert msg.artifact["99.score"] == {"ok": True, "value": 612}


def test_bad_ref_is_per_entry_error_not_a_raise():
    session = _seed()
    got = halo_fetch(session, ["99.score", "99.missing"])
    assert got["99.score"]["ok"] is True
    assert got["99.missing"]["ok"] is False
