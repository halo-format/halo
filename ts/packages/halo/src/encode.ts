// encode: bottom-up Merkle build, plus extend / merge.
//
// buildNode recurses children-first so a parent references children by handle, giving the
// Merkle property and free dedup (idempotent store.put). Returns { handle, envelope }.
// extend(root, name, value) folds a new branch onto an existing root (last write wins);
// merge(roots[]) combines several roots. Both reuse unchanged child handles and retain prior
// roots, giving version history for free.

export {};
