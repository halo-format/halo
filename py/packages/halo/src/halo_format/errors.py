"""Typed errors with shared meaning across ports.

UnknownHandle, HashMismatch (the tamper signal, never swallowed), WrongKind,
CanonicalizationError, StoreError.
"""


class HaloError(Exception):
    """Base class for all Halo errors."""


class UnknownHandle(HaloError):
    """A handle is absent from the store."""


class HashMismatch(HaloError):
    """Read bytes do not verify against the requested handle — the tamper signal."""


class WrongKind(HaloError):
    """walk was called on a leaf, or fetch on a branch."""


class CanonicalizationError(HaloError):
    """A value cannot be canonicalized (e.g. a non-finite number)."""


class StoreError(HaloError):
    """Wraps an adapter-level store failure."""
