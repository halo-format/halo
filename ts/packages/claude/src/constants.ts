// Names shared between the hook (which must exclude these tools) and the MCP server (which defines
// them). Kept in one place so the exclusion and the registration can never drift apart.

export const HALO_MCP_SERVER = "halo";
// One navigation tool only. halo_fetch is the single batch API the model ever sees: it pulls leaves
// AND, when a ref lands on a branch, returns that branch's sub-shape — so there is no second tool
// (no halo_walk) to choose between or confuse a leaf ref with.
export const HALO_FETCH_TOOL = "halo_fetch";

// In-process MCP tools are exposed to the model (and to hooks) as `mcp__<server>__<tool>`.
export const HALO_TOOL_PREFIX = `mcp__${HALO_MCP_SERVER}__`;

/** True for the adapter's own navigation tools — the results the encode hook must NOT re-encode. */
export function isHaloNavTool(toolName: string): boolean {
  return toolName.startsWith(HALO_TOOL_PREFIX);
}
