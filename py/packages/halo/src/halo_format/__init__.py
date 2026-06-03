"""Public surface of halo_format.

Producer:  encode, extend, merge
Consumer:  open_ -> Navigator(walk, fetch, fetch_many, root); free walk/fetch/fetch_many
Stores:    MemoryStore, FileStore
Errors:    UnknownHandle, HashMismatch, WrongKind, CanonicalizationError, StoreError

Re-exports only; implementation lives in the sibling modules.
"""
