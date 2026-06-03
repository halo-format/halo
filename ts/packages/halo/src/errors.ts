// errors: typed error classes with shared meaning across ports.
//
//   UnknownHandle        handle absent from the store
//   HashMismatch         bytes do not verify — the tamper signal, never swallowed
//   WrongKind            walk on a leaf, or fetch on a branch
//   CanonicalizationError a value cannot be canonicalized (e.g. non-finite number)
//   StoreError           wraps adapter-level failures

export class HaloError extends Error {
  constructor(message: string) {
    super(message);
    // new.target keeps the name correct under subclassing and minification.
    this.name = new.target.name;
  }
}

export class UnknownHandle extends HaloError {}
export class HashMismatch extends HaloError {}
export class WrongKind extends HaloError {}
export class CanonicalizationError extends HaloError {}
export class StoreError extends HaloError {}
