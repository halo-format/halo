"""Bottom-up Merkle build, plus extend / merge.

_build_node recurses children-first so a parent references its children by handle, which gives the
tree its Merkle structure and free dedup (store.put is idempotent and content-keyed). encode returns
{"handle", "envelope"}. extend(root, name, value) folds a new branch onto an existing root (last
write wins on name collision); merge(roots) combines several roots' branch tables. Both reuse every
unchanged child handle, so the only new node is the root, and because nodes are immutable the prior
root stays in the store — version history and a change audit for free.

Sync to match the Python Store (see store.py's note on the async divergence from TypeScript).
"""

from .carve import auto_carve
from .envelope import build_envelope
from .errors import WrongKind
from .node import branch_node, decode, is_branch, leaf_node, serialize
from .summarize import derive_summary


def _build_node(value, path, store, carve, summarize):
    """Build one node and everything beneath it, returning the node's handle."""
    decision = carve(value, path)
    if decision["as"] == "leaf":
        node = leaf_node(value)
    else:
        branches = {}
        for name, child in decision["children"].items():
            branches[name] = _build_node(child, path + [name], store, carve, summarize)
        summary = decision.get("summary")
        if summary is None:
            summary = summarize(value, branches)
        node = branch_node(summary, branches)
    return store.put(serialize(node))


def _result_for(root, store, alg):
    """Read the stored root node back and wrap it in an envelope."""
    root_node = decode(store.get(root))
    return {"handle": root, "envelope": build_envelope(root, root_node, alg)}


def encode(value, store, *, carve=None, summarize=None, alg="sha256"):
    """Encode a JSON value into content-addressed nodes and return its halo."""
    carve = carve or auto_carve
    summarize = summarize or derive_summary
    root = _build_node(value, [], store, carve, summarize)
    return _result_for(root, store, alg)


def _read_branch(root, store):
    node = decode(store.get(root))
    if not is_branch(node):
        raise WrongKind("extend/merge expect a branch root")
    return node


def extend(root, name, value, store, *, carve=None, summarize=None, alg="sha256"):
    """Fold `value` onto `root` as a new branch named `name` (last write wins on collision)."""
    carve = carve or auto_carve
    summarize = summarize or derive_summary
    base = _read_branch(root, store)
    child_handle = _build_node(value, [name], store, carve, summarize)
    branches = {**base["branches"], name: child_handle}
    new_root = store.put(serialize(branch_node(summarize(value, branches), branches)))
    return _result_for(new_root, store, alg)


def merge(roots, store, *, summarize=None, alg="sha256"):
    """Combine several roots' branch tables into one new root (last write wins, in order)."""
    summarize = summarize or derive_summary
    branches = {}
    for root in roots:
        node = _read_branch(root, store)
        branches = {**branches, **node["branches"]}
    new_root = store.put(serialize(branch_node(summarize(None, branches), branches)))
    return _result_for(new_root, store, alg)
