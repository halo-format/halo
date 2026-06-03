// Bundled helper for the Halo skill (code-execution path only).
//
// Re-exports the @halo-format/halo core surface — encode / walk / fetch / fetchMany — bound to a
// default in-process store, so a skill-loaded agent gets the light deployment with nothing to
// configure. Each encoded result is registered under a session map id (m1, m2, ...), so you can
// address branches by readable ref (e.g. `m1.income`) and the long handle stays the verification
// key. Every read verifies; a HashMismatch means the data was altered and must not be trusted.
//
// This path is best-effort: it only fires if the model routes data through code. When the host can
// install a deterministic adapter (e.g. the Claude PostToolUse hook in @halo-format/claude), use
// that for the plumbing and let the skill be guidance only.

import {
  encode as coreEncode,
  Navigator,
  MemoryStore,
  type HaloEnvelope,
  type JsonValue,
  type WalkResult,
  type FetchResult,
} from "@halo-format/halo";

const store = new MemoryStore();
let navigator: Navigator | null = null;
let n = 0;

/** Encode a result into the default store and return its halo. Only the envelope need enter context. */
export async function encode(value: JsonValue): Promise<{ handle: string; envelope: HaloEnvelope }> {
  const result = await coreEncode(value, { store });
  result.envelope.source = { id: `m${++n}` }; // session map id, so `m1.income`-style refs resolve
  if (navigator) navigator.register(result.envelope);
  else navigator = new Navigator(result.envelope, store);
  return result;
}

function nav(): Navigator {
  if (!navigator) throw new Error("encode a result before navigating");
  return navigator;
}

/** Expand a branch ref to its summary and child refs, without pulling leaf data. */
export async function walk(ref: string): Promise<WalkResult> {
  return nav().walk(ref);
}

/** Fetch a single leaf ref, verified on read. */
export async function fetch(ref: string): Promise<JsonValue> {
  return nav().fetch(ref);
}

/**
 * Fetch several leaf refs in one call, verified per-ref. Prefer this over single fetches: each call
 * is a round trip, so gather every ref a step needs and pull them together. One bad entry (e.g. a
 * HashMismatch) is surfaced for that ref and never sinks the batch.
 */
export async function fetchMany(refs: string[]): Promise<Record<string, FetchResult>> {
  return nav().fetchMany(refs);
}

export { store, MemoryStore, Navigator };
export type { HaloEnvelope };
