// Names shared between the hook (which must exclude these tools) and the MCP server (which defines
// them). Kept in one place so the exclusion and the registration can never drift apart.

export const HALO_MCP_SERVER = "halo";
// One navigation tool only. halo_fetch is the single batch API the model ever sees: it pulls leaves
// AND, when a ref lands on a branch, returns that branch's sub-shape — so there is no second tool
// (no halo_walk) to choose between or confuse a leaf ref with.
export const HALO_FETCH_TOOL = "halo_fetch";

// In-process MCP tools are exposed to the model (and to hooks) as `mcp__<server>__<tool>`.
export const HALO_TOOL_PREFIX = `mcp__${HALO_MCP_SERVER}__`;

// The model-facing description of halo_fetch. Shared so the Agent SDK MCP tool (nav-tools) and the
// raw Messages API tool definition (raw) describe the one tool identically and can never drift.
export const HALO_FETCH_DESCRIPTION =
  "The one tool for reading a halo map. Pass ALL the refs a step needs in one call (refs is an " +
  "array) rather than one at a time — each call is a separate round trip. A ref like `m1.income` " +
  "(or a raw `h:` handle) that points at a value returns it as `{ok:true,value}`; a ref that points " +
  "at a [branch] returns `{ok:true,kind:'branch',fields:[…]}` listing its sub-refs to fetch next. " +
  "An entry with `ok:false` (e.g. HashMismatch) means that data must not be trusted.";

/** True for the adapter's own navigation tools — the results the encode hook must NOT re-encode. */
export function isHaloNavTool(toolName: string): boolean {
  return toolName.startsWith(HALO_TOOL_PREFIX);
}
