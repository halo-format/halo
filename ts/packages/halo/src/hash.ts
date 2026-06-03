// hash: canonical bytes -> handle.
//
// handle = "h:" + lowercaseHex(sha256(canonical(node))), full 64-hex digest. Algorithm is
// pluggable behind a tiny registry keyed by `alg` (default sha256); the envelope declares
// it per-tree. Leaf dependency, byte-exact across ports.

import { createHash } from "node:crypto";
import type { Alg, Handle, JsonValue } from "./types.js";
import { canonicalBytes } from "./canonical.js";

// Algorithm registry keyed by `alg`. A future move (e.g. blake3) registers a function here and
// the envelope's `alg` selects it; call sites never hard-code the algorithm.
const REGISTRY: Record<Alg, (bytes: Uint8Array) => string> = {
  sha256: (bytes) => createHash("sha256").update(bytes).digest("hex"),
};

/** Hash canonical bytes into a handle: "h:" + lowercase hex digest under `alg`. */
export function hashBytes(bytes: Uint8Array, alg: Alg = "sha256"): Handle {
  const fn = REGISTRY[alg];
  if (!fn) throw new Error(`unknown hash alg: ${alg}`);
  return "h:" + fn(bytes);
}

/** Convenience: handle of a JSON value = hashBytes(canonicalBytes(value)). */
export function handleOf(value: JsonValue, alg: Alg = "sha256"): Handle {
  return hashBytes(canonicalBytes(value), alg);
}
