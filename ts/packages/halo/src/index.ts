// Public surface of @halo-format/halo.
//
// Producer:  encode, extend, merge
// Consumer:  open -> Navigator{ walk, fetch, fetchMany, root }; free walk/fetch/fetchMany
// Stores:    MemoryStore, FileStore
// Types:     Handle, Node, HaloEnvelope, Store, CarvePolicy, EncodeOptions
// Errors:    UnknownHandle, HashMismatch, WrongKind, CanonicalizationError, StoreError
//
// Re-exports only; implementation lives in the sibling modules.

export {};
