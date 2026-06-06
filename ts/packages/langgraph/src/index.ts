// @halo-format/langgraph — Halo host adapter for LangChain agents and LangGraph graphs.
//
// The interception point is LangChain's `wrapToolCall` middleware — a deterministic wrap-the-tool-call
// hook, the direct analog of the Claude Agent SDK's PostToolUse. Above a size threshold it encodes a
// tool result into a shared store and rewrites the ToolMessage the model sees: `content` becomes a
// SHAPE MAP (not the blob), and the full envelope rides in `artifact` (kept in graph state, never sent
// to the model). One plain LangChain tool, halo_fetch(refs[]), backed by the same store, lets the
// model pull back the withheld leaves (and expand branches), verified on read.
//
// installHalo(opts) returns the augmented `tools` and `middleware` arrays to splice into createAgent,
// plus the shared session:
//
//   const { tools, middleware, session } = installHalo({ tools: myTools });
//   const agent = createAgent({ model, tools, middleware });
//
// Note a JS/Python divergence: the JS `ToolNode` does not accept a wrap option, so on this host the
// middleware is the only clean surface — there is no haloToolNode() the way there is in Python.
//
// MANDATORY correctness rule: the middleware must NOT re-encode the navigation tool's own output, or a
// fetched leaf would be replaced by a new map and the model would never see the value. Enforced by an
// isHaloNavTool name check at the top of the wrapper.
//
// Light vs. heavy: pass `store: new FileStore(dir)` for cross-process persistence, and wrap navigation
// with the L2 chain, without touching the control flow here.

import { HaloSession, type SessionOptions } from "./session.js";
import { createHaloMiddleware } from "./middleware.js";
import { createHaloFetchTool } from "./nav-tool.js";

export type InstallHaloOptions = SessionOptions & {
  /** Your tools; the halo_fetch navigation tool is appended. */
  tools?: unknown[];
  /** Your middleware; the Halo encode middleware is appended. */
  middleware?: unknown[];
  /** Below this many bytes a tool result passes through unchanged (no encode). Default 2048. */
  threshold?: number;
  /** A pre-built session to share state with, instead of creating one. */
  session?: HaloSession;
};

export type InstallHaloResult = {
  /** Your tools plus the halo_fetch tool — pass to `createAgent({ tools })`. */
  tools: unknown[];
  /** Your middleware plus the Halo encode middleware — pass to `createAgent({ middleware })`. */
  middleware: unknown[];
  /** The shared session (store + map registry), for audit swaps or direct inspection. */
  session: HaloSession;
};

/**
 * Wire the Halo adapter into a createAgent setup. Append the returned `tools` and `middleware` to the
 * call. Returns the shared session for the audit/persistence swaps and inspection.
 */
export function installHalo(opts: InstallHaloOptions = {}): InstallHaloResult {
  const session = opts.session ?? new HaloSession(opts);
  const middleware = createHaloMiddleware(session, opts.threshold);
  const fetchTool = createHaloFetchTool(session);

  return {
    tools: [...(opts.tools ?? []), fetchTool],
    middleware: [...(opts.middleware ?? []), middleware],
    session,
  };
}

export { HaloSession } from "./session.js";
export type { SessionOptions, IngestResult, FetchEntry } from "./session.js";
export { createHaloMiddleware, rewrite } from "./middleware.js";
export { createHaloFetchTool, haloFetch } from "./nav-tool.js";
export { argJoin } from "./accumulate.js";
export type { KeyOf } from "./accumulate.js";
export { sizeOf, parseToolOutput, serializeEnvelope, shapeOf, previewOf } from "./serialize.js";
export type { FieldHint } from "./serialize.js";
export { HALO_FETCH_TOOL, isHaloNavTool } from "./constants.js";
