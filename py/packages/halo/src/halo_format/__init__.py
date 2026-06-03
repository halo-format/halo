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
from .carve import auto_carve, make_auto_carve
from .encode import encode, extend, merge
from .envelope import build_envelope
from .hash import handle_of, hash_bytes
from .node import (
    branch_node,
    decode,
    is_branch,
    is_leaf,
    leaf_node,
    node_handle,
    serialize,
)
from .store import FileStore, MemoryStore
from .summarize import derive_summary

__all__ = [
    "canonical",
    "canonical_bytes",
    "hash_bytes",
    "handle_of",
    "branch_node",
    "leaf_node",
    "is_branch",
    "is_leaf",
    "serialize",
    "node_handle",
    "decode",
    "auto_carve",
    "make_auto_carve",
    "derive_summary",
    "build_envelope",
    "encode",
    "extend",
    "merge",
    "MemoryStore",
    "FileStore",
    "HaloError",
    "UnknownHandle",
    "HashMismatch",
    "WrongKind",
    "CanonicalizationError",
    "StoreError",
]
