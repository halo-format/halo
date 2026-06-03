// hash: canonical bytes -> handle.
//
// handle = "h:" + lowercaseHex(sha256(canonical(node))), full 64-hex digest. Algorithm is
// pluggable behind a tiny registry keyed by `alg` (default sha256); the envelope declares
// it per-tree. Leaf dependency, byte-exact across ports.

export {};
