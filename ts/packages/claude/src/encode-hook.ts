// The encode hook — the plumbing. It fires after every qualifying tool returns, encodes the result
// into the session store, and replaces what the model sees with the envelope (the map). This is
// deterministic and model-independent: the payload is out of context before the model is involved,
// so the model cannot leak a full result by forgetting to navigate.
//
// Two passthrough conditions, in order:
//   1. The tool IS one of the halo navigation tools. MANDATORY: re-encoding a fetched leaf would
//      replace it with a new map and the model would never receive the value. The installer also
//      excludes these via the matcher, but this in-hook guard is the load-bearing one.
//   2. The result is below the size threshold. Encoding a small result costs a map plus a fetch
//      round trip for no benefit, so it passes through untouched.

import type { PostToolUseHookInput, HookJSONOutput } from "@anthropic-ai/claude-agent-sdk";
import type { HaloSession } from "./session.js";
import { isHaloNavTool } from "./constants.js";
import { sizeOf, parseToolOutput, serializeEnvelope } from "./serialize.js";

export type EncodeHookOptions = { threshold?: number };

const DEFAULT_THRESHOLD = 2048;

const PASSTHROUGH: HookJSONOutput = {};

export type EncodeHook = (input: PostToolUseHookInput) => Promise<HookJSONOutput>;

/** Build the PostToolUse encode hook bound to a session. */
export function createEncodeHook(session: HaloSession, opts: EncodeHookOptions = {}): EncodeHook {
  const threshold = opts.threshold ?? DEFAULT_THRESHOLD;

  return async (input: PostToolUseHookInput): Promise<HookJSONOutput> => {
    if (isHaloNavTool(input.tool_name)) return PASSTHROUGH; // never re-encode a fetched leaf
    if (sizeOf(input.tool_response) < threshold) return PASSTHROUGH;

    const value = parseToolOutput(input.tool_response);
    if (value === undefined) return PASSTHROUGH;

    const { envelope } = await session.ingest(input.tool_name, input.tool_input, value);
    return {
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        updatedToolOutput: serializeEnvelope(envelope),
      },
    };
  };
}
