"""The node model and its (de)serialization.

    BranchNode = {"k": "b", "summary": str, "branches": {name: Handle}}
    LeafNode   = {"k": "l", "value": JsonValue}

The k kind tag is part of the hashed content so a leaf and branch can never collide. Stored form
is canonical(node) bytes, not the object.
"""

import json

from .canonical import canonical_bytes
from .errors import HaloError
from .hash import hash_bytes


def branch_node(summary: str, branches: dict) -> dict:
    """Build a branch node. A shallow copy keeps it independent of the caller's map."""
    return {"k": "b", "summary": summary, "branches": dict(branches)}


def leaf_node(value) -> dict:
    return {"k": "l", "value": value}


def is_branch(node: dict) -> bool:
    return node.get("k") == "b"


def is_leaf(node: dict) -> bool:
    return node.get("k") == "l"


def serialize(node: dict) -> bytes:
    """The exact bytes that get hashed and stored for a node: canonical(node)."""
    return canonical_bytes(node)


def node_handle(node: dict, alg: str = "sha256") -> str:
    """A node's handle: hash over its canonical bytes. The Merkle building block."""
    return hash_bytes(serialize(node), alg)


def decode(data: bytes) -> dict:
    """Decode stored bytes back into a validated node.

    In normal use the bytes were verified against a handle first (navigate verifies on read), so
    decode of verified bytes always succeeds; the validation here guards malformed input, it is
    not a security boundary.
    """
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise HaloError(f"node bytes are not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise HaloError("node must be a JSON object")
    kind = obj.get("k")
    if kind == "l":
        if "value" not in obj:
            raise HaloError("leaf node missing `value`")
        return {"k": "l", "value": obj["value"]}
    if kind == "b":
        if not isinstance(obj.get("summary"), str):
            raise HaloError("branch node `summary` must be a string")
        branches = obj.get("branches")
        if not isinstance(branches, dict):
            raise HaloError("branch node `branches` must be an object")
        for name, h in branches.items():
            if not isinstance(h, str):
                raise HaloError(f'branch handle for "{name}" must be a string')
        return {"k": "b", "summary": obj["summary"], "branches": branches}
    raise HaloError(f"unknown node kind: {kind!r}")
