#!/usr/bin/env python3
"""Generate the shared conformance vectors for canonical/ and handles/.

The committed JSON files under ../vectors are the source of truth that every language port
asserts against. This script (re)generates them from a curated input set using rfc8785 as the
canonicalization oracle and stdlib sha256 for handles.

Why this is trustworthy and not circular: the TypeScript port implements canonicalization with a
*different* library (canonicalize, RFC 8785 reference impl). The two were cross-checked and agree
byte-for-byte, so the vectors encode RFC 8785 truth, and a port reproducing them is a real
cross-implementation check, not a tautology.

Control characters are written into the JSON as \\uXXXX escapes by json.dump, so the vector files
stay valid, portable JSON. Inputs are built with chr() so this source file contains no literal
control bytes.

Run:  python3 conformance/tools/generate_vectors.py
Requires:  rfc8785  (pip install rfc8785)
"""

import hashlib
import json
import os

import rfc8785

VECTORS_DIR = os.path.join(os.path.dirname(__file__), "..", "vectors")


def handle_of(value):
    canon = rfc8785.dumps(value)  # bytes, UTF-8
    digest = hashlib.sha256(canon).hexdigest()
    return canon.decode("utf-8"), "h:" + digest


# Curated input sets, grouped by the sharp edge they defend. Each case is (name, value).
CATEGORIES = {
    "numbers": [
        ("int-zero", 0),
        ("neg-zero", -0.0),                       # ECMAScript: serializes to "0"
        ("int-one", 1),
        ("int-neg-one", -1),
        ("float-1_5", 1.5),
        ("float-neg-1_5", -1.5),
        ("float-0_1", 0.1),
        ("float-0_5", 0.5),
        ("pi-double", 3.141592653589793),
        ("exp-1e21", 1e21),                       # "1e+21": exponent kicks in at 1e21
        ("exp-1e20", 1e20),                       # "100000000000000000000": still positional
        ("exp-1e-7", 1e-7),                       # "1e-7"
        ("exp-1e-6", 1e-6),                        # "0.000001": still positional
        ("int-100", 100),
        ("float-100", 100.0),                     # collapses to "100"
        ("safe-int-max", 9007199254740991),       # 2^53 - 1
        ("safe-int-min", -9007199254740991),
        ("double-rounding", 123456789.987654321),  # rounds to nearest double
        ("subnormal-min", 5e-324),
        ("double-near-max", 1.7976931348623157e308),
        ("machine-epsilon", 2.220446049250313e-16),
        ("avogadro", 6.022e23),
        ("neg-small", -0.000001),
    ],
    "strings": [
        ("empty", ""),
        ("ascii", "hello"),
        ("embedded-quote", "a\"b"),
        ("whitespace-escapes", "tab\tnl\n cr\r"),
        ("short-escapes", "bsp \b ff \f end"),
        ("control-chars", "ctrl " + chr(0) + " " + chr(1) + " " + chr(0x1F) + " end"),
        ("del-not-escaped", "del " + chr(0x7F) + " end"),
        ("backslash", "backslash \\ end"),
        ("forward-slash", "slash / fwd"),          # JCS does NOT escape "/"
        ("latin1", "caf" + chr(0xE9)),             # café
    ],
    "unicode": [
        ("astral-emoji", chr(0x1F600)),            # 😀 (surrogate pair)
        ("astral-clef", chr(0x1D11E)),             # 𝄞
        ("bmp-cjk", chr(0x4E2D) + chr(0x6587)),    # 中文
        # key ordering by UTF-16 code unit: space, A, a, b10, b2, é(U+00E9), 😀(astral)
        ("key-order-mixed", {"z": 1, "a": 2, "caf" + chr(0xE9): 3,
                             chr(0x1F600): 4, "A": 5, " ": 6, "b10": 7, "b2": 8}),
        ("key-order-astral-vs-bmp", {chr(0x1F600): 1, chr(0xFFFF): 2, "z": 3}),
    ],
    "structure": [
        ("true", True),
        ("false", False),
        ("null", None),
        ("empty-object", {}),
        ("empty-array", []),
        ("array-ints", [1, 2, 3]),
        ("array-nested-empty-array", [[]]),
        ("array-nested-empty-object", [{}]),
        ("deep-nest", {"x": [1, {"y": 2}], "": None,
                       "nested": {"deep": {"deeper": [True, False, None]}}}),
        ("mixed-array", {"mixed": [1, "two", 3.5, True, None, {}, []]}),
        ("empty-key", {"": "empty-key-value"}),
    ],
}


# --- whole-tree envelope vectors -------------------------------------------------------------
#
# These pin the encode pipeline (carve + summarize + envelope), not just JCS. The carve/summarize
# rules are Halo's own spec, so they are reimplemented HERE against the rfc8785 oracle rather than
# imported from halo_format — that keeps the byte-level handles independent of the port under test
# (every handle below is rfc8785-derived) while still asserting the structural rules both ports
# implement. Must stay in lockstep with carve.py/summarize.py/envelope.py (defaults: array
# threshold 25, inline byte threshold 1024).

ARRAY_THRESHOLD = 25
INLINE_BYTES = 1024


def _derive_summary(branches):
    # Names sorted by UTF-16 code unit (via UTF-16-BE), matching the ports.
    names = sorted(branches.keys(), key=lambda s: s.encode("utf-16-be"))
    n = len(names)
    if n == 0:
        return "0 branches"
    if n == 1:
        return f"1 branch: {names[0]}"
    return f"{n} branches: {', '.join(names)}"


def _leaf_summary(value):
    if value is None:
        return "leaf: null"
    if isinstance(value, bool):  # before int/float: bool is an int subclass
        return "leaf: boolean"
    if isinstance(value, (int, float)):
        return "leaf: number"
    if isinstance(value, str):
        return "leaf: string"
    if isinstance(value, list):
        return f"leaf: array of {len(value)} items"
    return f"leaf: object with {len(value)} keys"


def _auto_carve(value):
    """Returns (kind, children) where kind is 'leaf' or 'branch'. Mirrors autoCarve defaults."""
    if isinstance(value, dict):
        if not value:
            return ("leaf", None)
        if len(rfc8785.dumps(value)) <= INLINE_BYTES:
            return ("leaf", None)
        return ("branch", dict(value))
    if isinstance(value, list):
        if len(value) <= ARRAY_THRESHOLD:
            return ("leaf", None)
        children = {}
        chunks = (len(value) + ARRAY_THRESHOLD - 1) // ARRAY_THRESHOLD
        for i in range(chunks):
            children[str(i)] = value[i * ARRAY_THRESHOLD : (i + 1) * ARRAY_THRESHOLD]
        return ("branch", children)
    return ("leaf", None)  # primitives (None, bool, number, str)


def _build(value):
    """Bottom-up: returns (handle, node) for the subtree rooted at value."""
    kind, children = _auto_carve(value)
    if kind == "leaf":
        node = {"k": "l", "value": value}
    else:
        branches = {name: _build(child)[0] for name, child in children.items()}
        node = {"k": "b", "summary": _derive_summary(branches), "branches": branches}
    handle = "h:" + hashlib.sha256(rfc8785.dumps(node)).hexdigest()
    return handle, node


def _envelope(value):
    root_h, root_node = _build(value)
    if root_node["k"] == "b":
        view = {"summary": root_node["summary"], "branches": root_node["branches"]}
    else:
        view = {"summary": _leaf_summary(value), "branches": {}}
    return {"halo": "1", "alg": "sha256", "root": root_h, "view": view}


# Whole-tree cases, default autoCarve. Inputs chosen to exercise: leaf roots (primitive, short
# array, small object), a carved branch root, a nested branch, array chunking, and the chunk
# boundary on both sides (25 inlines, 26 splits).
ENVELOPE_CASES = [
    ("leaf-root-int", 42),
    ("leaf-root-array", [1, 2, 3]),
    ("leaf-root-small-object", {"a": 1}),
    ("branch-root", {"a": "x" * 2000, "b": 1, "c": [1, 2, 3]}),
    ("nested-branch", {"outer": {"inner": "y" * 2000, "k": 1}, "z": "w" * 2000}),
    ("array-leaf-25", list(range(25))),
    ("array-chunk-boundary-26", list(range(26))),
    ("array-chunked-60", list(range(60))),
]

# source is envelope-only metadata and MUST NOT enter any hash. Each case pairs two distinct source
# blocks; the harness builds both envelopes and asserts the root (and view) are unchanged.
SOURCE_CASES = [
    (
        "source-not-hashed",
        {"a": "x" * 2000, "b": 1},
        {"id": "m1"},
        {"id": "m2", "tool": "get_customer", "args": [123], "ts": "2026-01-01T00:00:00Z"},
    ),
]


def build_node_cases():
    """Node-level vectors: a node object -> its canonical bytes -> its handle.

    A node is hashed exactly like any other JSON value, so handle_of(node) gives the node handle.
    Branch nodes reference real child handles (computed from child leaf nodes), so these vectors
    also pin the Merkle wiring: a branch's bytes contain its children's handles.
    """
    cases = []

    # Leaf nodes wrapping a range of value kinds.
    for name, value in [
        ("leaf-int", 42),
        ("leaf-float", 3.5),
        ("leaf-string", "hello"),
        ("leaf-bool", True),
        ("leaf-null", None),
        ("leaf-object", {"a": 1, "b": [2, 3]}),
        ("leaf-array", [1, "two", None]),
        ("leaf-empty-object", {}),
    ]:
        cases.append(("node-" + name, {"k": "l", "value": value}))

    # Branch node over real child leaf handles (the credit-report shape from the design doc).
    income_leaf = {"k": "l", "value": {"monthly": 4200}}
    debts_leaf = {"k": "l", "value": {"monthly": 2604}}
    _, income_h = handle_of(income_leaf)
    _, debts_h = handle_of(debts_leaf)
    cases.append(("node-branch-two", {
        "k": "b",
        "summary": "2 branches: debts, income",
        "branches": {"income": income_h, "debts": debts_h},
    }))

    # Branch with no children — an empty map root is still a valid branch node.
    cases.append(("node-branch-empty", {"k": "b", "summary": "0 branches", "branches": {}}))

    # Nested branch: a branch whose child is itself a branch handle.
    _, inner_h = handle_of({"k": "b", "summary": "0 branches", "branches": {}})
    cases.append(("node-branch-nested", {
        "k": "b",
        "summary": "1 branch: child",
        "branches": {"child": inner_h},
    }))

    return cases


def main():
    canonical_dir = os.path.join(VECTORS_DIR, "canonical")
    handles_dir = os.path.join(VECTORS_DIR, "handles")
    os.makedirs(canonical_dir, exist_ok=True)
    os.makedirs(handles_dir, exist_ok=True)

    for category, cases in CATEGORIES.items():
        canon_cases = []
        handle_cases = []
        for name, value in cases:
            canon, handle = handle_of(value)
            canon_cases.append({"name": name, "input": value, "canonical": canon})
            handle_cases.append({"name": name, "input": value, "handle": handle})

        with open(os.path.join(canonical_dir, category + ".json"), "w", encoding="utf-8") as f:
            json.dump({"description": f"canonical form ({category})", "cases": canon_cases},
                      f, ensure_ascii=True, indent=2)
            f.write("\n")
        with open(os.path.join(handles_dir, category + ".json"), "w", encoding="utf-8") as f:
            json.dump({"description": f"handle ({category})", "alg": "sha256", "cases": handle_cases},
                      f, ensure_ascii=True, indent=2)
            f.write("\n")
        print(f"{category}: {len(cases)} cases -> canonical/{category}.json, handles/{category}.json")

    # nodes/ vectors: node object -> canonical bytes -> handle.
    nodes_dir = os.path.join(VECTORS_DIR, "nodes")
    os.makedirs(nodes_dir, exist_ok=True)
    node_cases = []
    for name, node in build_node_cases():
        canon, handle = handle_of(node)
        node_cases.append({"name": name, "node": node, "canonical": canon, "handle": handle})
    with open(os.path.join(nodes_dir, "nodes.json"), "w", encoding="utf-8") as f:
        json.dump({"description": "node -> canonical bytes -> handle", "alg": "sha256",
                   "cases": node_cases}, f, ensure_ascii=True, indent=2)
        f.write("\n")
    print(f"nodes: {len(node_cases)} cases -> nodes/nodes.json")

    # envelopes/ vectors: whole-tree input -> expected envelope (default autoCarve).
    envelopes_dir = os.path.join(VECTORS_DIR, "envelopes")
    os.makedirs(envelopes_dir, exist_ok=True)
    env_cases = [{"name": name, "input": value, "envelope": _envelope(value)}
                 for name, value in ENVELOPE_CASES]
    with open(os.path.join(envelopes_dir, "envelopes.json"), "w", encoding="utf-8") as f:
        json.dump({"description": "whole-tree: input -> expected envelope (default autoCarve)",
                   "alg": "sha256", "cases": env_cases}, f, ensure_ascii=True, indent=2)
        f.write("\n")
    print(f"envelopes: {len(env_cases)} cases -> envelopes/envelopes.json")

    # source.json: confirm source is never hashed (two sources -> same root).
    source_cases = [{"name": name, "input": value, "source_a": a, "source_b": b,
                     "root": _envelope(value)["root"]}
                    for name, value, a, b in SOURCE_CASES]
    with open(os.path.join(envelopes_dir, "source.json"), "w", encoding="utf-8") as f:
        json.dump({"description": "source is envelope-only and never hashed", "alg": "sha256",
                   "cases": source_cases}, f, ensure_ascii=True, indent=2)
        f.write("\n")
    print(f"source: {len(source_cases)} cases -> envelopes/source.json")


if __name__ == "__main__":
    main()
