// summarize: (value, branches) -> deterministic summary string for a branch node.
//
// The summary is part of the hashed node, so it MUST be a pure function of structural facts and
// never LLM prose, or the same value would yield different handles and content-addressing breaks.
// deriveSummary depends only on the branch names (count + sorted names), which makes it identical
// for encode, extend, and merge alike — none of those reconstruct the aggregate value.
//
// Names are sorted by UTF-16 code unit, matching JCS key ordering, so the string is byte-identical
// to the Python port (which sorts on the UTF-16-BE encoding for the same reason).

import type { Handle, JsonValue } from "./types.js";

export type Summarizer = (value: JsonValue, branches: Record<string, Handle>) => string;

/** Deterministic structural summary of a branch: "<n> branches: <sorted names>". */
export const deriveSummary: Summarizer = (_value, branches) => {
  const names = Object.keys(branches).sort(); // JS default sort = UTF-16 code unit order
  const n = names.length;
  if (n === 0) return "0 branches";
  if (n === 1) return `1 branch: ${names[0]}`;
  return `${n} branches: ${names.join(", ")}`;
};
