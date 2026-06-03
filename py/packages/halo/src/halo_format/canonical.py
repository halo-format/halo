"""value -> canonical bytes (RFC 8785 JCS).

The interop crux and a leaf dependency. Keys sorted by UTF-16 code unit, JCS string escaping,
ECMAScript Number-to-String for numbers. v1 allows non-integer floats and leans on a vetted JCS
library here. Must be byte-identical to the TypeScript port; defended by
conformance/vectors/canonical.
"""

import math

import rfc8785

from .errors import CanonicalizationError


def _assert_canonicalizable(value):
    """Reject non-finite floats up front so the error matches across ports.

    bool is a subclass of int in Python; rfc8785 handles it correctly, and we never treat a bool
    as a number here, so no special-casing is needed.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"non-finite number cannot be canonicalized: {value!r}")
    elif isinstance(value, dict):
        for v in value.values():
            _assert_canonicalizable(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _assert_canonicalizable(v)


def canonical_bytes(value) -> bytes:
    """Canonical RFC 8785 (JCS) bytes (UTF-8) of a JSON value — the exact bytes that get hashed."""
    _assert_canonicalizable(value)
    try:
        return rfc8785.dumps(value)
    except CanonicalizationError:
        raise
    except Exception as e:  # rfc8785 raises its own/ValueError for unrepresentable input
        raise CanonicalizationError(str(e)) from e


def canonical(value) -> str:
    """Canonical RFC 8785 (JCS) string form of a JSON value."""
    return canonical_bytes(value).decode("utf-8")
