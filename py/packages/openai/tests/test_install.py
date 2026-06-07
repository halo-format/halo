"""install_halo: appends the halo_fetch tool non-destructively, returns the filter to put on the run,
and shares one session. Plus the nav tool's pure helper end-to-end against an ingested map."""

from agents import function_tool

from halo_format_openai import (
    HaloSession,
    create_halo_fetch_tool,
    halo_fetch,
    install_halo,
)
from halo_format_openai.constants import HALO_FETCH_TOOL

BIG = '{"profile":{"income":{"monthly":4200}},"filler":"' + "x" * 3000 + '"}'


@function_tool
def existing(x: int) -> dict:
    """An existing tool."""
    return {"x": x}


def test_install_halo_appends_tool_preserving_existing():
    result = install_halo(tools=[existing])
    assert [t.name for t in result.tools] == ["existing", HALO_FETCH_TOOL]
    assert callable(result.call_model_input_filter)
    assert isinstance(result.session, HaloSession)


def test_install_halo_with_no_inputs():
    result = install_halo()
    assert [t.name for t in result.tools] == [HALO_FETCH_TOOL]


def test_install_halo_shares_passed_session():
    session = HaloSession()
    result = install_halo(tools=[existing], session=session)
    assert result.session is session


def test_fetch_tool_is_a_function_tool():
    tool = create_halo_fetch_tool(HaloSession())
    assert tool.name == HALO_FETCH_TOOL
    # schema derived from the list[str] hint
    assert tool.params_json_schema["properties"]["refs"]["type"] == "array"


def test_halo_fetch_helper_end_to_end():
    # encode a map, then the pure fetch helper pulls a verified leaf and expands a branch. The value is
    # padded past the inline-carve threshold so top-level fields become navigable branches.
    session = HaloSession(now=lambda: "T")
    value = {"income": {"monthly": 4200, "annual": 50400, "pad": "y" * 2000}, "score": 612}
    session.ingest("bureau", {"applicant": 99}, value)
    res = halo_fetch(session, ["99.score", "99.income"])
    assert res["99.score"] == {"ok": True, "value": 612}
    assert res["99.income"]["kind"] == "branch"  # a branch ref returns its sub-shape, not an error
