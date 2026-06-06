"""install_halo (the create_agent path) and halo_tool_node (the StateGraph path): both append the
navigation tool and wire the wrapper non-destructively, and both share one session."""

from langchain_core.tools import tool

from halo_format_langgraph import (
    HaloMiddleware,
    HaloSession,
    halo_tool_node,
    install_halo,
)
from halo_format_langgraph.constants import HALO_FETCH_TOOL


@tool
def existing(x: int) -> dict:
    """An existing tool."""
    return {"x": x}


def test_install_halo_appends_tool_and_middleware_preserving_existing():
    class OtherMW:  # a stand-in for the host's own middleware
        pass

    other = OtherMW()
    result = install_halo(tools=[existing], middleware=[other])

    assert [t.name for t in result.tools] == ["existing", HALO_FETCH_TOOL]
    assert result.middleware[0] is other
    assert isinstance(result.middleware[-1], HaloMiddleware)
    assert isinstance(result.session, HaloSession)


def test_install_halo_with_no_inputs():
    result = install_halo()
    assert [t.name for t in result.tools] == [HALO_FETCH_TOOL]
    assert len(result.middleware) == 1


def test_install_halo_shares_passed_session():
    session = HaloSession()
    result = install_halo(tools=[existing], session=session)
    assert result.session is session


def test_halo_tool_node_builds_node_with_appended_tool():
    result = halo_tool_node([existing])
    assert [t.name for t in result.tools] == ["existing", HALO_FETCH_TOOL]
    assert isinstance(result.session, HaloSession)
    assert result.tool_node is not None
