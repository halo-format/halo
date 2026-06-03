// errors: typed error classes with shared meaning across ports.
//
//   UnknownHandle        handle absent from the store
//   HashMismatch         bytes do not verify — the tamper signal, never swallowed
//   WrongKind            walk on a leaf, or fetch on a branch
//   CanonicalizationError a value cannot be canonicalized (e.g. non-finite number)
//   StoreError           wraps adapter-level failures

export {};
