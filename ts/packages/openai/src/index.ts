// @halo-format/openai — Halo host adapter for the OpenAI Agents SDK.
//
// Host divergence (read this first). The Python `openai-agents` SDK exposes a
// `RunConfig.call_model_input_filter` that rewrites the assembled model input before each model call,
// and the Python adapter uses it. The released JS `@openai/agents` SDK (0.1.x) has NO such hook — its
// only model-input filter is `handoffInputFilter` (handoffs only). So this TS adapter intercepts one
// layer down, at the Model boundary: `wrapModel` / `wrapModelProvider` rewrite the tool-result items in
// `request.input` before delegating to the real model. Same interception point in the pipeline (right
// before the model call) and the same generic reach (every tool's output flows through the model
// request), just expressed against the surface this SDK actually exposes.
//
// Above a size threshold a large tool result becomes a SHAPE MAP (root kind + one line per field: ref,
// kind, bounded preview), so the payload stays out of the model's context. One function tool,
// halo_fetch(refs[]), backed by the same store, lets the model pull back the withheld leaves (and
// expand branches), verified on read.
//
// installHalo(opts) returns the augmented `tools`, the `wrapModel`/`wrapModelProvider` helpers bound to
// the session+threshold, and the shared session. Two wiring styles:
//
//   // a) wrap a Model instance:
//   const { tools, wrapModel, session } = installHalo({ tools: myTools });
//   const agent = new Agent({ name, model: wrapModel(myModel), tools });
//
//   // b) wrap the provider (when the agent names its model by string):
//   const { tools, wrapModelProvider } = installHalo({ tools: myTools });
//   const runner = new Runner({ modelProvider: wrapModelProvider(myProvider) });
//   await runner.run(new Agent({ name, model: "gpt-4.1", tools }), input);
//
// MANDATORY correctness rule: the wrapper must NOT re-encode the navigation tool's own output, or a
// fetched leaf would be replaced by a new map and the model would never see the value. Enforced by an
// isHaloNavTool check on each result item's `name`.
//
// Light vs. heavy: pass `store: new FileStore(dir)` for cross-process persistence, and wrap navigation
// with the L2 chain, without touching the control flow here.

import type { Model, ModelProvider } from "@openai/agents";
import { HaloSession, type SessionOptions } from "./session.js";
import { createHaloFetchTool } from "./nav-tool.js";
import { wrapModel as wrapModelImpl, wrapModelProvider as wrapModelProviderImpl } from "./model-wrapper.js";

export type InstallHaloOptions = SessionOptions & {
  /** Your tools; the halo_fetch navigation tool is appended. */
  tools?: unknown[];
  /** Below this many bytes a tool result passes through unchanged (no encode). Default 2048. */
  threshold?: number;
  /** A pre-built session to share state with, instead of creating one. */
  session?: HaloSession;
};

export type InstallHaloResult = {
  /** Your tools plus the halo_fetch tool — pass to `new Agent({ tools })`. */
  tools: unknown[];
  /** Wrap a Model instance so its tool results are encoded before the model sees them. */
  wrapModel: (model: Model) => Model;
  /** Wrap a ModelProvider so every model it resolves is Halo-wrapped (for `new Runner({ modelProvider })`). */
  wrapModelProvider: (provider: ModelProvider) => ModelProvider;
  /** The shared session (store + map registry), for audit swaps or direct inspection. */
  session: HaloSession;
};

/**
 * Wire the Halo adapter into an OpenAI Agents SDK setup. Append the returned `tools` to your Agent and
 * wrap your model (or model provider) with the returned helper. Returns the shared session for the
 * audit/persistence swaps and inspection.
 */
export function installHalo(opts: InstallHaloOptions = {}): InstallHaloResult {
  const session = opts.session ?? new HaloSession(opts);
  const threshold = opts.threshold;
  const fetchTool = createHaloFetchTool(session);

  return {
    tools: [...(opts.tools ?? []), fetchTool],
    wrapModel: (model: Model) => wrapModelImpl(model, session, threshold),
    wrapModelProvider: (provider: ModelProvider) => wrapModelProviderImpl(provider, session, threshold),
    session,
  };
}

export { HaloSession } from "./session.js";
export type { SessionOptions, IngestResult, FetchEntry } from "./session.js";
export { createHaloFetchTool, haloFetch } from "./nav-tool.js";
export { wrapModel, wrapModelProvider, rewriteInput, DEFAULT_THRESHOLD } from "./model-wrapper.js";
export { argJoin } from "./accumulate.js";
export type { KeyOf } from "./accumulate.js";
export { sizeOf, parseToolOutput, serializeEnvelope, shapeOf, previewOf } from "./serialize.js";
export type { FieldHint } from "./serialize.js";
export { HALO_FETCH_TOOL, isHaloNavTool } from "./constants.js";
