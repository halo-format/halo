"""Public surface of halo_format.

Producer:  encode, extend, merge
Consumer:  open_ -> Navigator(walk, fetch, fetch_many, root); free walk/fetch/fetch_many
Stores:    MemoryStore, FileStore
Errors:    UnknownHandle, HashMismatch, WrongKind, CanonicalizationError, StoreError

Re-exports only; implementation lives in the sibling modules.
"""

from .canonical import canonical, canonical_bytes
from .errors import (
    CanonicalizationError,
    HaloError,
    HashMismatch,
    StoreError,
    UnknownHandle,
    WrongKind,
)
from .hash import handle_of, hash_bytes

__all__ = [
    "canonical",
    "canonical_bytes",
    "hash_bytes",
    "handle_of",
    "HaloError",
    "UnknownHandle",
    "HashMismatch",
    "WrongKind",
    "CanonicalizationError",
    "StoreError",
]
