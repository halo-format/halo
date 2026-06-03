// @halo-format/claude — Halo host adapter for the Claude Agent SDK.
//
// installHalo(options, { threshold, keyOf }) augments the SDK options with:
//   - a PostToolUse encode hook that, above a size threshold, encodes a tool result into the
//     shared MemoryStore and sets updatedToolOutput to the envelope (the map), not the blob;
//   - an in-process MCP server exposing halo_walk(ref) and halo_fetch(refs[]) backed by the
//     same store, for the model to pull back the withheld leaves, verified on read.
//
// MANDATORY correctness rule: the hook matcher MUST exclude the halo navigation tools, or
// fetched leaves would be re-encoded and the model would never see the actual value.
//
// keyOf drives entity accumulation (default argJoin): related calls fold into one growing map
// per entity via core extend. Plumbing (the hook) is deterministic; guidance (the Skill) shapes
// how the model navigates.

export {};
