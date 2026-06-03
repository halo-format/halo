"""The node model and its (de)serialization.

    BranchNode = {"k": "b", "summary": str, "branches": {name: Handle}}
    LeafNode   = {"k": "l", "value": JsonValue}

The k kind tag is part of the hashed content so a leaf and branch can never collide. Stored form
is canonical(node) bytes, not the object.
"""
