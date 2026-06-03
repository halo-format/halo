"""Build the root envelope — the only thing that crosses into the model's context.

    {"halo": "1", "alg": ..., "root": ..., "view": {"summary", "branches"}, "source"?: ...}

view inlines the root node's content so a consumer navigates with zero fetches and can verify by
re-hashing the reconstructed root against root. source is envelope-only identification metadata
(id, tool, args, ts) and is NEVER hashed. (Full envelope verification and source population land
with the navigator/adapter; this module is the builder the encode pipeline returns.)
"""

from .node import is_branch


def _leaf_summary(value):
    """A leaf root has no branches; describe its shape instead. Structural + cross-port identical."""
    if value is None:
        return "leaf: null"
    if isinstance(value, bool):  # before int/float: bool is an int subclass in Python
        return "leaf: boolean"
    if isinstance(value, (int, float)):
        return "leaf: number"
    if isinstance(value, str):
        return "leaf: string"
    if isinstance(value, list):
        return f"leaf: array of {len(value)} items"
    return f"leaf: object with {len(value)} keys"


def build_envelope(root, root_node, alg="sha256"):
    """Build the envelope for an already-stored root node."""
    if is_branch(root_node):
        view = {"summary": root_node["summary"], "branches": dict(root_node["branches"])}
    else:
        view = {"summary": _leaf_summary(root_node["value"]), "branches": {}}
    return {"halo": "1", "alg": alg, "root": root, "view": view}
