// The encode middleware — the plumbing. It wraps every tool call: it runs the tool via the handler,
// and above a size threshold rewrites the resulting ToolMessage so the model sees a SHAPE MAP instead
// of the blob, while the full payload goes to the store and the full envelope rides in the
// ToolMessage's `artifact` (kept in graph state, never serialized into the model's context). This is
// deterministic and model-independent: the payload is out of context before the model is involved, so
// the model cannot leak a full result by forgetting to navigate.
//
// The interception point is LangChain's `wrapToolCall` middleware hook (createMiddleware), the direct
// analog of the Claude SDK's PostToolUse. Note a JS/Python divergence: the JS `ToolNode` does not
// accept a wrap option, so on this host the middleware is the ONLY clean surface — there is no
// ToolNode-param path the way there is in Python.
//
// Two passthrough conditions, in order (mirrors the Claude encode hook):
//   1. The tool IS the halo navigation tool. MANDATORY: re-encoding a fetched leaf would replace it
//      with a new map and the model would never receive the value.
//   2. The ToolMessage content is below the size threshold, or is not JSON-ish — pass through.
//
// A non-ToolMessage return (a Command that updates graph state directly) always passes through: there
// is nothing to encode.

import { ToolMessage } from "@langchain/core/messages";
import { createMiddleware } from "langchain";
import type { HaloSession } from "./session.js";
import { isHaloNavTool } from "./constants.js";
import { sizeOf, parseToolOutput, serializeEnvelope } from "./serialize.js";

const DEFAULT_THRESHOLD = 2048;

// Where an upstream tool's own artifact is preserved if Halo needs the slot for its envelope, so a
// tool that already used content_and_artifact does not silently lose its data.
const PRIOR_ARTIFACT_KEY = "halo_prior_artifact";

// The minimal shape the wrapper reads off a ToolCallRequest. The full type comes from langchain; we
// only touch `toolCall.name` and `toolCall.args`, so a structural type keeps the helper testable
// without constructing a whole runtime request.
type HasToolCall = { toolCall: { name: string; args: unknown; id?: string } };

/**
 * Encode a tool's ToolMessage and return a rewritten copy: content -> shape map, artifact -> envelope.
 * Returns the value untouched when it should pass through (not a ToolMessage, small, or non-JSON).
 * Builds a NEW ToolMessage rather than mutating, so a handler that returns a shared/cached message is
 * never clobbered and the rewrite survives serialization (LangChain messages serialize from their
 * constructor args). The original tool_call_id, name and status are preserved.
 */
export async function rewrite(
  session: HaloSession,
  threshold: number,
  msg: unknown,
  request: HasToolCall,
): Promise<unknown> {
  if (!(msg instanceof ToolMessage)) return msg; // a Command (state update) or other return
  if (sizeOf(msg.content) < threshold) return msg;
  const value = parseToolOutput(msg.content);
  if (value === undefined) return msg;

  const { envelope } = await session.ingest(request.toolCall.name, request.toolCall.args, value);
  const hints = await session.describe(envelope);

  const additional_kwargs =
    msg.artifact !== undefined && msg.artifact !== null
      ? { ...msg.additional_kwargs, [PRIOR_ARTIFACT_KEY]: msg.artifact }
      : msg.additional_kwargs;

  return new ToolMessage({
    content: serializeEnvelope(envelope, hints), // the SHAPE MAP (model-visible)
    artifact: envelope, // full envelope (out of context, persisted in state)
    tool_call_id: msg.tool_call_id,
    name: msg.name,
    status: msg.status,
    id: msg.id,
    additional_kwargs,
  });
}

/**
 * Build the Halo encode middleware bound to a session, for `createAgent({ middleware: [...] })`.
 * Provides the sync/async-agnostic `wrapToolCall` hook (the handler is awaited).
 */
export function createHaloMiddleware(session: HaloSession, threshold: number = DEFAULT_THRESHOLD) {
  return createMiddleware({
    name: "HaloMiddleware",
    wrapToolCall: async (request, handler) => {
      if (isHaloNavTool(request.toolCall.name)) return handler(request); // never re-encode a leaf
      const msg = await handler(request);
      return (await rewrite(session, threshold, msg, request)) as typeof msg;
    },
  });
}
