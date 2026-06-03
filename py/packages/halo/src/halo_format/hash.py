"""canonical bytes -> handle.

handle = "h:" + sha256(canonical(node)).hexdigest(), full 64-hex. Algorithm pluggable behind a
small registry keyed by alg (default sha256); the envelope declares it per-tree. Uses stdlib
hashlib. Leaf dependency, byte-exact across ports.
"""
