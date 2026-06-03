// @halo-format/claude — Halo host adapter for the Claude Agent SDK.
//
// installHalo(options, opts?) augments the SDK options with:
//   - a PostToolUse encode hook that, above a size threshold, encodes a tool result into a shared
//     store and sets updatedToolOutput to the envelope (the map), not the blob;
//   - an in-process MCP server exposing halo_walk(ref) and halo_fetch(refs[]) backed by the same
//     store, for the model to pull back the withheld leaves, verified on read.
//
// One call to adopt the adapter. Plumbing (the hook) is deterministic and fires always; the Skill
// (loaded separately by the host) is guidance that shapes how the model navigates. The two stay
// separate on purpose: a weak Skill costs some efficiency but never the core property — the payload
// is out of context regardless.
//
// MANDATORY correctness rule: the hook must NOT re-encode the halo navigation tools' own output, or
// a fetched leaf would be replaced by a new map and the model would never see the value. This is
// enforced two ways: the matcher below excludes them by name, and the hook guards on tool name.
//
// Light vs. heavy (SDK integration, Section 7): pass `store: new FileStore(dir)` for cross-session
// persistence, and wrap navigation with the L2 chain, without touching the control flow here.

import type {
  Options,
  HookCallback,
  HookCallbackMatcher,
  PostToolUseHookInput,
  HookJSONOutput,
} from "@anthropic-ai/claude-agent-sdk";
import { HaloSession, type SessionOptions } from "./session.js";
import { createEncodeHook } from "./encode-hook.js";
import { createNavServer } from "./nav-tools.js";
import { HALO_MCP_SERVER, HALO_TOOL_PREFIX } from "./constants.js";

export type InstallHaloOptions = SessionOptions & {
  /** Below this many bytes a tool result passes through unchanged (no encode). Default 2048. */
  threshold?: number;
  /** A pre-built session to share state with, instead of creating one. */
  session?: HaloSession;
};

// Matches every tool name EXCEPT the halo navigation tools, so the encode hook skips them. The
// in-hook guard is the load-bearing exclusion; this matcher is the belt to its suspenders.
const NOT_HALO_TOOLS = `^(?!${HALO_TOOL_PREFIX})`;

export type InstallHaloResult = {
  /** The augmented SDK options to pass to `query()`. */
  options: Options;
  /** The shared session (store + map registry), for audit swaps or direct inspection. */
  session: HaloSession;
};

/** Wire the Halo adapter into a set of SDK options. Returns the augmented options and the session. */
export function installHalo(options: Options, opts: InstallHaloOptions = {}): InstallHaloResult {
  const session = opts.session ?? new HaloSession(opts);
  const encode = createEncodeHook(session, { threshold: opts.threshold });

  // The matcher scopes this to PostToolUse, so input is always a PostToolUseHookInput at runtime.
  const callback: HookCallback = async (input) => {
    if (input.hook_event_name !== "PostToolUse") return {} as HookJSONOutput;
    return encode(input as PostToolUseHookInput);
  };
  const matcher: HookCallbackMatcher = { matcher: NOT_HALO_TOOLS, hooks: [callback] };

  const augmented: Options = {
    ...options,
    hooks: {
      ...options.hooks,
      PostToolUse: [...(options.hooks?.PostToolUse ?? []), matcher],
    },
    mcpServers: {
      ...options.mcpServers,
      [HALO_MCP_SERVER]: createNavServer(session),
    },
  };

  return { options: augmented, session };
}

export { HaloSession } from "./session.js";
export type { SessionOptions, IngestResult } from "./session.js";
export { createEncodeHook } from "./encode-hook.js";
export type { EncodeHook, EncodeHookOptions } from "./encode-hook.js";
export { createNavServer, haloWalk, haloFetch } from "./nav-tools.js";
export { argJoin } from "./accumulate.js";
export type { KeyOf } from "./accumulate.js";
export { sizeOf, parseToolOutput, serializeEnvelope } from "./serialize.js";
export {
  HALO_MCP_SERVER,
  HALO_WALK_TOOL,
  HALO_FETCH_TOOL,
  HALO_TOOL_PREFIX,
  isHaloNavTool,
} from "./constants.js";
