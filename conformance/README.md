# Conformance vectors

The shared, language-neutral interop spine. Every language port loads these vectors and asserts
against them in CI. A halo produced by the TypeScript SDK must verify and navigate under Python
and vice versa, which is only guaranteed if both ports agree on these vectors byte-for-byte.

## Vector kinds

```
vectors/
  canonical/    input value      -> expected canonical string/bytes
  handles/      input value      -> expected handle ("h:" + sha256 hex)
  nodes/        node object      -> expected canonical bytes -> expected handle
  envelopes/    whole input tree -> expected envelope
```

## What the vectors are weighted toward

The sharp edges where independent implementations diverge:

- **Number formatting** — the main risk. v1 allows non-integer floats, so this is covered heavily:
  integers, large magnitudes, exponents, negative zero, fractional values via ECMAScript
  Number-to-String.
- **Unicode** — key ordering by UTF-16 code unit, astral (surrogate-pair) characters in keys and
  string values, JCS string escaping.
- **Structure** — empty objects and empty arrays, deep nesting, array chunking boundaries.

## How a port consumes the vectors

Each port has a small harness (`ts/conformance`, `py/conformance`) that reads the JSON vector
files here and asserts: canonical bytes match, handles match, node handles match, and envelopes
match (excluding the non-hashed `source` field). The vectors are the source of truth; ports
conform to them, not the other way round.

## Format

Vector files are JSON. Each file documents its own `input` and `expected` shape. Vectors are not
frozen until the canonical + hash modules are green in both ports.
