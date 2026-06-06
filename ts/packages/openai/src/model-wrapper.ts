// The encode plumbing for the OpenAI Agents SDK (TypeScript) — a Model wrapper.
//
// IMPORTANT host divergence from the Python adapter. The Python `openai-agents` SDK exposes a
// `RunConfig.call_model_input_filter` that rewrites the assembled model input before each model call;
// the released JS `@openai/agents` SDK (0.1.x) has NO such hook (only `handoffInputFilter`, which fires
// on handoffs, not on every model call). So on this host we intercept one layer down, at the Model
// boundary: we wrap the `Model` so that `getResponse`/`getStreamedResponse` rewrite the tool-result
// items in `request.input` before delegating to the real model. This is the SAME interception point in
// the pipeline — immediately before the model sees the input — and it is equally GENERIC: every tool's
// output (built-in, function, external/MCP/hosted) flows through the model request, so all of it is
// caught, not just tools we own.
//
// Two consequences of intercepting at model-input time rather than tool-return time, both handled here:
//
// 1. Idempotency. The wrapper fires on every model call and sees the whole input list each time, so a
//    per-callId cache (callId -> rendered shape map) makes repeated firings stable: the first sighting
//    of a result is ingested (assigning a stable map id) and rendered; every later turn reuses the
//    cached string, so refs the model already saw never shift and a result is never re-encoded.
//
// 2. Correlating args. A `function_call_result` item carries `name` (so the nav-tool exclusion is a
//    direct check) but not the call arguments. We index the `function_call` items in the same input
//    list (callId -> arguments) so `keyOf` entity accumulation sees the real arguments.
//
// The core guarantee is unchanged: the rewrite happens before the model call, so the raw blob never
// reaches the model. The store is the envelope's only home on this host (no LangGraph-style artifact).

import type { Model, ModelProvider, ModelRequest } from "@openai/agents";
import type { HaloSession } from "./session.js";
import { isHaloNavTool } from "./constants.js";
import { sizeOf, parseToolOutput, serializeEnvelope } from "./serialize.js";

export const DEFAULT_THRESHOLD = 2048;

// A shape map starts with this marker; a passthrough guard so an already-encoded output (e.g. one
// persisted into history, seen by a fresh wrapper with no cache entry) is never re-ingested.
const SHAPE_MAP_PREFIX = "[halo] map";

// The minimal structural shapes the wrapper reads off the SDK's protocol items. The real items carry
// more, but we only touch these fields, so a structural type keeps the wrapper testable without
// constructing whole SDK objects.
type CallItem = { type: "function_call"; callId: string; name: string; arguments?: string };
type ResultOutput = { type: "text"; text: string } | { type: string; [k: string]: unknown };
type ResultItem = {
  type: "function_call_result";
  callId: string;
  name: string;
  output: ResultOutput;
};
type InputItem = { type?: string; [k: string]: unknown };

function isCall(item: InputItem): item is CallItem {
  return item.type === "function_call";
}
function isResult(item: InputItem): item is ResultItem {
  return item.type === "function_call_result";
}
function isTextOutput(o: ResultOutput): o is { type: "text"; text: string } {
  return o?.type === "text" && typeof (o as { text?: unknown }).text === "string";
}

/** Index callId -> parsed arguments from the function_call items, so a result (which lacks args) can be
 * given the real call arguments for keyOf entity accumulation. */
function indexCalls(items: InputItem[]): Map<string, unknown> {
  const args = new Map<string, unknown>();
  for (const item of items) {
    if (!isCall(item) || typeof item.callId !== "string") continue;
    let parsed: unknown = item.arguments;
    if (typeof item.arguments === "string") {
      try {
        parsed = JSON.parse(item.arguments);
      } catch {
        parsed = item.arguments;
      }
    }
    args.set(item.callId, parsed);
  }
  return args;
}

function looksEncoded(text: string): boolean {
  return text.trimStart().startsWith(SHAPE_MAP_PREFIX);
}

/**
 * Rewrite a model request's `input`: replace each large tool-result output with a shape map, encoding
 * the payload into the session store. Pure over its (session, cache, threshold); returns a NEW input
 * array (and new items for the ones it changes), never mutating the SDK's objects. A string input (the
 * very first user turn, no tool results yet) is returned unchanged.
 */
export async function rewriteInput(
  session: HaloSession,
  cache: Map<string, string>,
  threshold: number,
  input: ModelRequest["input"],
): Promise<ModelRequest["input"]> {
  if (typeof input === "string" || !Array.isArray(input)) return input;
  const items = input as InputItem[];
  const callArgs = indexCalls(items);

  const out = [...items];
  let changed = false;
  for (let i = 0; i < items.length; i++) {
    const item = items[i]!;
    if (!isResult(item) || !isTextOutput(item.output)) continue;
    const callId = item.callId;
    const text = item.output.text;

    // Idempotency: a call we already rewrote reuses its cached shape map verbatim.
    const cached = cache.get(callId);
    if (cached !== undefined) {
      if (text !== cached) {
        out[i] = { ...item, output: { type: "text", text: cached } };
        changed = true;
      }
      continue;
    }

    if (isHaloNavTool(item.name)) continue; // MANDATORY: never re-encode a fetched leaf
    if (looksEncoded(text)) continue; // already a shape map (no cache entry) — leave it
    if (sizeOf(text) < threshold) continue;
    const value = parseToolOutput(text);
    if (value === undefined) continue;

    const { envelope } = await session.ingest(item.name, callArgs.get(callId), value);
    const shapeMap = serializeEnvelope(envelope, await session.describe(envelope));
    cache.set(callId, shapeMap);
    out[i] = { ...item, output: { type: "text", text: shapeMap } };
    changed = true;
  }

  return changed ? (out as ModelRequest["input"]) : input;
}

/**
 * Wrap a Model so its requests have large tool results swapped for shape maps before the model sees
 * them. The cache is per-wrapped-model (one run's lifetime), keeping repeated firings idempotent.
 */
export function wrapModel(
  model: Model,
  session: HaloSession,
  threshold: number = DEFAULT_THRESHOLD,
): Model {
  const cache = new Map<string, string>();
  return {
    async getResponse(request: ModelRequest) {
      const input = await rewriteInput(session, cache, threshold, request.input);
      return model.getResponse({ ...request, input });
    },
    getStreamedResponse(request: ModelRequest) {
      async function* gen() {
        const input = await rewriteInput(session, cache, threshold, request.input);
        yield* model.getStreamedResponse({ ...request, input });
      }
      return gen();
    },
  };
}

/**
 * Wrap a ModelProvider so every model it resolves is Halo-wrapped. Pass the result on
 * `new Runner({ modelProvider })` — the ergonomic path when the agent names its model by string.
 */
export function wrapModelProvider(
  provider: ModelProvider,
  session: HaloSession,
  threshold: number = DEFAULT_THRESHOLD,
): ModelProvider {
  return {
    async getModel(modelName?: string): Promise<Model> {
      const model = await provider.getModel(modelName);
      return wrapModel(model, session, threshold);
    },
  };
}
