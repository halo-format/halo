// carve: (value, path) -> CarveDecision { as: "leaf" } | { as: "branch", children }.
//
// autoCarve default: split a non-empty object into one branch per key; chunk arrays longer than a
// threshold (default 25) into contiguous slices; inline everything below a small byte threshold as
// a leaf. Hosts/skills override with task knowledge — an explicit carve (e.g. the credit example
// naming income, debts, ...) always wins over the default. Bounds node size so no single node need
// be the whole payload. Pure and deterministic: the carve shape is part of what gets hashed.

import type { JsonValue } from "./types.js";
import { canonicalBytes } from "./canonical.js";

export type CarveDecision =
  | { as: "leaf" }
  | { as: "branch"; children: Record<string, JsonValue>; summary?: string };

export type CarvePolicy = (value: JsonValue, path: string[]) => CarveDecision;

export type AutoCarveOptions = {
  arrayThreshold?: number; // arrays longer than this are chunked; shorter inline as one leaf
  inlineBytes?: number; // objects whose canonical bytes are <= this inline as one leaf
};

const LEAF: CarveDecision = { as: "leaf" };

function isPlainObject(v: JsonValue): v is { [k: string]: JsonValue } {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/** Build an autoCarve policy with custom thresholds. `autoCarve` is this with the defaults. */
export function makeAutoCarve({
  arrayThreshold = 25,
  inlineBytes = 1024,
}: AutoCarveOptions = {}): CarvePolicy {
  return function autoCarve(value, _path) {
    if (isPlainObject(value)) {
      const entries = Object.entries(value);
      if (entries.length === 0) return LEAF; // {} is a terminal leaf, not a branch
      if (canonicalBytes(value).length <= inlineBytes) return LEAF; // small object inlines whole
      const children: Record<string, JsonValue> = {};
      for (const [k, v] of entries) children[k] = v;
      return { as: "branch", children };
    }
    if (Array.isArray(value)) {
      if (value.length <= arrayThreshold) return LEAF; // short array inlines as one leaf
      const children: Record<string, JsonValue> = {};
      const chunks = Math.ceil(value.length / arrayThreshold);
      for (let i = 0; i < chunks; i++) {
        children[String(i)] = value.slice(i * arrayThreshold, (i + 1) * arrayThreshold);
      }
      return { as: "branch", children }; // each chunk re-carves to a leaf (length <= threshold)
    }
    return LEAF; // primitives (null, boolean, number, string) are always leaves
  };
}

/** The default carve policy: object-by-key, chunk long arrays, inline small subtrees. */
export const autoCarve: CarvePolicy = makeAutoCarve();
