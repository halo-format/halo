"""value -> canonical bytes (RFC 8785 JCS).

The interop crux and a leaf dependency. Keys sorted by UTF-16 code unit, JCS string escaping,
ECMAScript Number-to-String for numbers. v1 allows non-integer floats and leans on a vetted JCS
library here. Must be byte-identical to the TypeScript port; defended by
conformance/vectors/canonical.
"""
