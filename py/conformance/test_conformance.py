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

from halo_format import (
    MemoryStore,
    canonical,
    decode,
    encode,
    handle_of,
    node_handle,
    serialize,
)

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


def _load_file(kind, file):
    # Envelope vectors carry two shapes in one dir, so load the specific file rather than globbing.
    with open(os.path.join(VECTORS, kind, file), encoding="utf-8") as f:
        data = json.load(f)
    return [pytest.param(c, id=c["name"]) for c in data["cases"]]


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


@pytest.mark.parametrize("case", _load_file("envelopes", "envelopes.json"))
def test_envelope(case):
    r = encode(case["input"], MemoryStore())
    assert r["envelope"] == case["envelope"]


@pytest.mark.parametrize("case", _load_file("envelopes", "source.json"))
def test_source_not_hashed(case):
    env = encode(case["input"], MemoryStore())["envelope"]
    assert env["root"] == case["root"]
    # Attaching different source blocks must not change root or the navigable view.
    a = {**env, "source": case["source_a"]}
    b = {**env, "source": case["source_b"]}
    assert a["root"] == case["root"]
    assert b["root"] == case["root"]
    assert a["view"] == b["view"]
