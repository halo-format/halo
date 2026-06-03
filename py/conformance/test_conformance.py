"""Conformance harness (Python).

Loads the shared vectors from ../../conformance/vectors and asserts halo_format matches them:
canonical bytes and handles. These are the same vectors the TypeScript harness runs, generated
with an independent JCS oracle (rfc8785), so both ports asserting against one shared set is what
guarantees a halo produced in one verifies and navigates in the other.
"""

import glob
import json
import os

import pytest

from halo_format import canonical, decode, handle_of, node_handle, serialize

VECTORS = os.path.join(os.path.dirname(__file__), "..", "..", "conformance", "vectors")


def _load(kind):
    cases = []
    for path in sorted(glob.glob(os.path.join(VECTORS, kind, "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        file = os.path.basename(path)
        for c in data["cases"]:
            cases.append(pytest.param(c, id=f"{file}::{c['name']}"))
    return cases


@pytest.mark.parametrize("case", _load("canonical"))
def test_canonical(case):
    assert canonical(case["input"]) == case["canonical"]


@pytest.mark.parametrize("case", _load("handles"))
def test_handle(case):
    assert handle_of(case["input"]) == case["handle"]


@pytest.mark.parametrize("case", _load("nodes"))
def test_node(case):
    node = case["node"]
    assert serialize(node).decode("utf-8") == case["canonical"]
    assert node_handle(node) == case["handle"]
    # round-trip: decode(serialize(node)) reconstructs the node
    assert decode(serialize(node)) == node
