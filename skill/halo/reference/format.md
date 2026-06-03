# Halo node and envelope format

Progressive-disclosure reference for the Halo skill. Read this only when you need the wire
details behind the map you are navigating.

## Nodes

A node is either a branch or a leaf. The node object is what gets hashed.

```
BranchNode = { "k": "b", "summary": <string>, "branches": { <name>: <handle> } }
LeafNode   = { "k": "l", "value": <any JSON value> }
```

The `k` kind tag is part of the hashed content, so a leaf and a branch can never collide. A
branch's `branches` map holds child *handles* (strings), so a branch hash transitively covers
every descendant — the root handle is a Merkle root over the whole value.

## Handles

```
handle = "h:" + lowercaseHex( sha256( canonical(node) ) )
```

The full 64-hex digest is the handle. Truncated prefixes are display-only and are never used as a
store key or for verification. `canonical` is RFC 8785 (JCS): keys sorted by UTF-16 code unit,
JCS string escaping, ECMAScript number formatting — so the same value always produces the same
handle, in every language port.

## Envelope

The only thing that enters your context. It inlines the root view so you can start navigating
with no fetch.

```
{
  "halo": "1",
  "alg": "sha256",
  "root": <handle>,
  "view": { "summary": <string>, "branches": { <name>: <handle> } },
  "source"?: {            // identification only — NOT hashed, cannot affect handles or dedup
    "id":   <string>,     // map id, e.g. "m1"
    "tool"?: <string>,
    "args"?: <any>,
    "ts"?:   <string>     // ISO timestamp
  }
}
```

You can verify an envelope by re-hashing the reconstructed root node (`{ "k": "b", summary,
branches }`) and comparing to `root`. Two tool calls returning identical data produce identical
handles and differ only in `source.id`.

## Refs

Instead of copying a 64-char handle you may address a branch by a map-scoped ref:

```
m1.income            a top-level branch of map m1
m1.income.monthly    a nested branch/leaf
```

The navigator resolves a ref to a handle via the registered envelope's branch table, then
verifies the resolved handle exactly as it would a raw handle. The ref is convenience; the handle
stays the verification key. Raw handles always work and need no registration.

## Reads, and what verification means

- `walk(handle)` → `{ summary, branches }` for a branch. Cheap: structure and summary only, never
  leaf data.
- `fetch(handle)` → the leaf value, after recomputing its hash and confirming it matches.
- `fetchMany(refs)` → a per-ref record, each entry `{ ok: true, value }` or `{ ok: false, error }`.
  Batch several refs into one call to collapse round trips. One bad entry never sinks the batch.

A `HashMismatch` means the bytes did not verify against the handle you asked for — the data was
altered or the store returned the wrong bytes. Never trust a mismatched value.
