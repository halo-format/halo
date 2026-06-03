"""Names shared between the hook (which must exclude these tools) and the MCP server (which defines
them). Kept in one place so the exclusion and the registration can never drift apart."""

HALO_MCP_SERVER = "halo"
HALO_WALK_TOOL = "halo_walk"
HALO_FETCH_TOOL = "halo_fetch"

# In-process MCP tools are exposed to the model (and to hooks) as ``mcp__<server>__<tool>``.
HALO_TOOL_PREFIX = f"mcp__{HALO_MCP_SERVER}__"


def is_halo_nav_tool(tool_name: str) -> bool:
    """True for the adapter's own navigation tools — the results the encode hook must NOT re-encode."""
    return tool_name.startswith(HALO_TOOL_PREFIX)
