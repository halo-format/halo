"""End-to-end through a real compiled LangGraph: the ToolNode runs the tool, the Halo wrapper rewrites
the ToolMessage to a shape map, the envelope lands in the artifact, and the session navigates back the
withheld leaves — verified. Also covers entity accumulation across two calls sharing an argument."""

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from halo_format_langgraph import halo_tool_node

BIG = {"profile": {"income": {"monthly": 4200}, "debts": {"monthly": 2604}}, "filler": "x" * 3000}


@tool
def bureau_report(applicant: int) -> dict:
    """Get a bureau report."""
    return BIG


@tool
def get_appointments(applicant: int) -> dict:
    """Get appointments for an applicant."""
    return {"appointments": [{"id": i, "slot": f"2026-06-{i:02d}"} for i in range(1, 30)]}


def _graph(tools, **kw):
    result = halo_tool_node(tools, now=lambda: "T", **kw)
    g = StateGraph(MessagesState)
    g.add_node("tools", result.tool_node)
    g.add_edge(START, "tools")
    g.add_edge("tools", END)
    return g.compile(), result.session


def _call(name, args, cid):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid, "type": "tool_call"}])


def test_tool_result_is_withheld_and_navigable():
    app, session = _graph([bureau_report])
    out = app.invoke({"messages": [_call("bureau_report", {"applicant": 99}, "c1")]})
    tm = out["messages"][-1]

    assert tm.content.startswith('[halo] map "99"')
    assert tm.artifact["halo"] == "1"
    # the model never sees the payload; the session fetches it back, verified
    got = session.fetch(["99.profile"])["99.profile"]
    assert got == {"ok": True, "value": {"debts": {"monthly": 2604}, "income": {"monthly": 4200}}}


def test_nav_tool_runs_in_graph_and_is_not_re_encoded():
    app, session = _graph([bureau_report])
    app.invoke({"messages": [_call("bureau_report", {"applicant": 99}, "c1")]})
    out = app.invoke({"messages": [_call("halo_fetch", {"refs": ["99.profile"]}, "c2")]})
    ftm = out["messages"][-1]
    assert not ftm.content.startswith("[halo] map")  # passed through, not turned into a map
    assert "income" in ftm.content


def test_entity_accumulation_folds_two_calls_into_one_map():
    # threshold low enough that the (modest) appointments result also crosses it and is ingested.
    app, session = _graph([bureau_report, get_appointments], threshold=256)
    app.invoke({"messages": [_call("bureau_report", {"applicant": 123}, "c1")]})
    out = app.invoke({"messages": [_call("get_appointments", {"applicant": 123}, "c2")]})
    tm = out["messages"][-1]

    # second call for the same id folds in: the map is now namespaced by tool name
    assert tm.artifact["source"]["id"] == "123"
    branches = set(tm.artifact["view"]["branches"])
    assert {"bureau_report", "get_appointments"} <= branches
