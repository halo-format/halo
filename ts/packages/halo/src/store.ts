// store: the Store interface plus MemoryStore and FileStore.
//
//   put(bytes) -> Handle  (content-addressed, idempotent, stores once)
//   get(handle) -> Bytes  (throws UnknownHandle if absent)
//   has(handle) -> boolean
//   getMany?(handles) -> (Bytes | undefined)[]   (optional multi-get)
//
// Untrusted by design: every read verifies, so a buggy/hostile store cannot substitute data
// undetected. MemoryStore = in-process Map (the light deployment); FileStore = one file per
// handle under a dir (cross-step persistence in a sandbox).

export {};
