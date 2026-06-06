// The one name shared between the middleware (which must exclude it) and the navigation tool (which
// defines it). Kept in one place so the exclusion and the registration can never drift apart.
//
// Unlike the Claude adapter, the navigation tool here is a plain LangChain tool, not an in-process MCP
// server, so its name has no `mcp__<server>__` prefix — it is simply `halo_fetch` and the exclusion is
// a single string comparison.

// One navigation tool only. halo_fetch is the single batch API the model ever sees: it pulls leaves
// AND, when a ref lands on a branch, returns that branch's sub-shape — so there is no second tool
// (no halo_walk) to choose between or confuse a leaf ref with.
export const HALO_FETCH_TOOL = "halo_fetch";

/** True for the adapter's own navigation tool — the result the middleware must NOT re-encode. */
export function isHaloNavTool(toolName: string): boolean {
  return toolName === HALO_FETCH_TOOL;
}
