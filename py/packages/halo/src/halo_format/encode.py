"""Bottom-up Merkle build, plus extend / merge.

build_node recurses children-first so a parent references children by handle, giving the Merkle
property and free dedup (idempotent store.put). Returns (handle, envelope). extend(root, name,
value) folds a new branch onto an existing root (last write wins); merge(roots) combines several.
Both reuse unchanged child handles and retain prior roots (version history for free).
"""
