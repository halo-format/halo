"""Unit tests for node decode validation and the leaf/branch kind-tag separation. Happy-path
serialize/handle/round-trip behavior is covered by the shared node vectors in py/conformance."""

import pytest

from halo_format import (
    HaloError,
    branch_node,
    decode,
    is_branch,
    is_leaf,
    leaf_node,
    node_handle,
)


def test_leaf_constructor_and_guards():
    n = leaf_node(42)
    assert n == {"k": "l", "value": 42}
    assert is_leaf(n) is True
    assert is_branch(n) is False


def test_branch_constructor_defensive_copy():
    branches = {"a": "h:aa"}
    n = branch_node("one", branches)
    branches["a"] = "h:bb"  # mutate caller's map
    assert n["branches"]["a"] == "h:aa"  # node unaffected
    assert is_branch(n) is True


@pytest.mark.parametrize(
    "raw",
    [
        b"{bad",                                       # invalid JSON
        b"[1,2]",                                      # not an object
        b'{"k":"x"}',                                  # unknown kind
        b'{"k":"l"}',                                  # leaf missing value
        b'{"k":"b","summary":1,"branches":{}}',        # non-string summary
        b'{"k":"b","summary":"s","branches":{"a":1}}',  # non-string child handle
    ],
)
def test_decode_rejects_malformed(raw):
    with pytest.raises(HaloError):
        decode(raw)


def test_kind_tag_prevents_collision():
    leaf = leaf_node({"summary": "x", "branches": {}})
    branch = branch_node("x", {})
    assert node_handle(leaf) != node_handle(branch)
