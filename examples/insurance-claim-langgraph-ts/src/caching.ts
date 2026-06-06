// ============================================================================
// Anthropic prompt caching for the LangGraph agent (CACHE=1).
//
// ChatAnthropic does not cache by default, so every model turn re-sends the whole
// conversation as fresh input. This middleware sets moving cache breakpoints
// (cache_control: ephemeral) on the system message and the latest message before each
// model call. Anthropic then caches the growing conversation prefix once (a cache write,
// ~1.25x) and re-reads it on later turns at ~0.1x instead of full price.
//
// It applies to whichever agent it's added to, so the A/B stays fair: run baseline and
// Halo both with CACHE=1. Caching mostly changes *long* loops (where a big tool result is
// re-read many turns); a one-shot fetch sees little benefit because nothing re-reads it.
// ============================================================================
import { createMiddleware } from "langchain";

const EPHEMERAL = { type: "ephemeral" } as const;

// Return a clone of msg with a cache_control breakpoint on its last content block.
// `new msg.constructor({ ...msg, content })` rebuilds any message type (preserves
// tool_call_id, name, etc.).
function withBreakpoint(msg: any): any {
  const content = msg.content;
  let blocks: any[];
  if (typeof content === "string") {
    if (!content) return msg;
    blocks = [{ type: "text", text: content, cache_control: EPHEMERAL }];
  } else if (Array.isArray(content) && content.length) {
    blocks = content.map((b) => (b && typeof b === "object" ? { ...b } : { type: "text", text: String(b) }));
    blocks[blocks.length - 1] = { ...blocks[blocks.length - 1], cache_control: EPHEMERAL };
  } else {
    return msg;
  }
  return new msg.constructor({ ...msg, content: blocks });
}

// Moving Anthropic cache breakpoint on the system message + the latest message.
export const promptCachingMiddleware = createMiddleware({
  name: "PromptCachingMiddleware",
  wrapModelCall: async (request: any, handler: any) => {
    const messages = request.messages?.length
      ? [...request.messages.slice(0, -1), withBreakpoint(request.messages[request.messages.length - 1])]
      : request.messages;
    const next = { ...request, messages };
    if (request.systemMessage) next.systemMessage = withBreakpoint(request.systemMessage);
    return handler(next);
  },
});
