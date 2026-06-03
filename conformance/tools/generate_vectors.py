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


if __name__ == "__main__":
    main()
