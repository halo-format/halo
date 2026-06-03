"""canonical bytes -> handle.

handle = "h:" + sha256(canonical(node)).hexdigest(), full 64-hex. Algorithm pluggable behind a
small registry keyed by alg (default sha256); the envelope declares it per-tree. Uses stdlib
hashlib. Leaf dependency, byte-exact across ports.
"""

import hashlib

from .canonical import canonical_bytes

# Algorithm registry keyed by alg. A future move (e.g. blake3) registers a function here and the
# envelope's alg selects it; call sites never hard-code the algorithm.
_REGISTRY = {
    "sha256": lambda b: hashlib.sha256(b).hexdigest(),
}


def hash_bytes(data: bytes, alg: str = "sha256") -> str:
    """Hash canonical bytes into a handle: "h:" + lowercase hex digest under alg."""
    fn = _REGISTRY.get(alg)
    if fn is None:
        raise ValueError(f"unknown hash alg: {alg}")
    return "h:" + fn(data)


def handle_of(value, alg: str = "sha256") -> str:
    """Convenience: handle of a JSON value = hash_bytes(canonical_bytes(value))."""
    return hash_bytes(canonical_bytes(value), alg)
