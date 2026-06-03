// canonical: value -> canonical bytes (RFC 8785 JCS).
//
// The interop crux and a leaf dependency. Keys sorted by UTF-16 code unit, JCS string
// escaping (UTF-8 output), ECMAScript Number-to-String for numbers. v1 allows non-integer
// floats and leans on a vetted JCS library here rather than hand-rolling. Must be
// byte-identical to the Python port; defended by conformance/vectors/canonical.

import canonicalize from "canonicalize";
import type { JsonValue } from "./types.js";
import { CanonicalizationError } from "./errors.js";

// RFC 8785 forbids non-finite numbers, but JS's JSON.stringify (which the canonicalize library
// builds on) would silently turn NaN/Infinity into null. We reject them at the boundary so the
// behavior matches the Python port, which raises, rather than producing a divergent handle.
function assertCanonicalizable(value: JsonValue): void {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new CanonicalizationError(`non-finite number cannot be canonicalized: ${value}`);
    }
  } else if (Array.isArray(value)) {
    for (const item of value) assertCanonicalizable(item);
  } else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value)) {
      assertCanonicalizable((value as { [k: string]: JsonValue })[key] as JsonValue);
    }
  }
}

/** Canonical RFC 8785 (JCS) string form of a JSON value. */
export function canonical(value: JsonValue): string {
  assertCanonicalizable(value);
  const out = canonicalize(value as unknown);
  if (out === undefined) {
    throw new CanonicalizationError("value is not representable in canonical JSON");
  }
  return out;
}

/** Canonical bytes (UTF-8) of a JSON value — the exact bytes that get hashed. */
export function canonicalBytes(value: JsonValue): Uint8Array {
  return new TextEncoder().encode(canonical(value));
}
