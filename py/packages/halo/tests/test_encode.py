"""Unit tests for the encode pipeline: carve, summarize, encode, extend, merge. These defend the
load-bearing invariants (determinism, content-addressing, Merkle integrity, dedup) that the shared
whole-tree envelope vectors will later pin cross-port. CROSS_PORT_ROOT is the root handle the
TypeScript port produces for the same input — asserting it here is a real cross-implementation lock
without needing a vector file yet."""

import pytest

from halo_format import (
    MemoryStore,
    WrongKind,
    auto_carve,
    branch_node,
    decode,
    derive_summary,
    encode,
    extend,
    is_branch,
    leaf_node,
    make_auto_carve,
    merge,
    node_handle,
)

# The credit-report-shaped fixture, with a `note` big enough to force the top object to carve.
FIXTURE = {
    "income": {"monthly": 4200},
    "debts": {"monthly": 2604},
    "inquiries": [1, 2, 3],
    "tradelines": ["a", "b", "c", "d", "e", "f", "g"],
    "note": "x" * 2000,
}

# Root handle the TypeScript port produces for FIXTURE — the cross-port interop lock.
CROSS_PORT_ROOT = "h:41d7286f74ae2aeb6ca69823ddf25b9381dccba488602c1a8347a6b5eb163223"


def test_auto_carve_inlines_small_and_primitive():
    assert auto_carve(42, []) == {"as": "leaf"}
    assert auto_carve("s", []) == {"as": "leaf"}
    assert auto_carve(None, []) == {"as": "leaf"}
    assert auto_carve({}, []) == {"as": "leaf"}
    assert auto_carve([], []) == {"as": "leaf"}
    assert auto_carve({"a": 1}, []) == {"as": "leaf"}  # small object inlines


def test_auto_carve_carves_large_object():
    big = {"a": "x" * 2000, "b": 1}
    d = auto_carve(big, [])
    assert d["as"] == "branch"
    assert sorted(d["children"].keys()) == ["a", "b"]


def test_auto_carve_chunks_long_array():
    arr = list(range(60))
    d = make_auto_carve(array_threshold=25)(arr, [])
    assert d["as"] == "branch"
    assert list(d["children"].keys()) == ["0", "1", "2"]
    assert d["children"]["0"] == arr[0:25]
    assert d["children"]["2"] == arr[50:60]


def test_auto_carve_inline_bytes_zero_forces_branch():
    assert make_auto_carve(inline_bytes=0)({"a": 1}, [])["as"] == "branch"


def test_derive_summary_deterministic_and_sorted():
    assert derive_summary(None, {}) == "0 branches"
    assert derive_summary(None, {"child": "h:x"}) == "1 branch: child"
    assert derive_summary(None, {"income": "h:1", "debts": "h:2"}) == "2 branches: debts, income"


def test_encode_deterministic_and_cross_port():
    a = encode(FIXTURE, MemoryStore())
    b = encode(FIXTURE, MemoryStore())
    assert a["handle"] == b["handle"]
    assert a["handle"] == CROSS_PORT_ROOT
    assert a["envelope"] == b["envelope"]


def test_encode_envelope_shape():
    store = MemoryStore()
    r = encode(FIXTURE, store)
    env = r["envelope"]
    assert env["halo"] == "1"
    assert env["alg"] == "sha256"
    assert env["root"] == r["handle"]
    assert env["view"]["summary"] == "5 branches: debts, income, inquiries, note, tradelines"
    assert sorted(env["view"]["branches"].keys()) == [
        "debts",
        "income",
        "inquiries",
        "note",
        "tradelines",
    ]


def test_encode_content_addressed_root():
    store = MemoryStore()
    r = encode(FIXTURE, store)
    root_node = branch_node(r["envelope"]["view"]["summary"], r["envelope"]["view"]["branches"])
    assert node_handle(root_node) == r["handle"]


def test_encode_merkle_integrity():
    changed = {**FIXTURE, "income": {"monthly": 4201}}
    a = encode(FIXTURE, MemoryStore())
    b = encode(changed, MemoryStore())
    assert b["handle"] != a["handle"]


def test_encode_dedup_equal_subtrees():
    store = MemoryStore()
    sub = {"blob": "y" * 2000}
    encode({"left": sub, "right": sub, "pad": "z" * 2000}, store)
    # root + 3 children, but left and right share one leaf -> 4 nodes, not 5
    assert len(store) == 4


def test_encode_leaf_root():
    store = MemoryStore()
    env = encode([1, 2, 3], store)["envelope"]
    assert env["view"]["summary"] == "leaf: array of 3 items"
    assert env["view"]["branches"] == {}


def test_extend_reuses_children_and_retains_prior_root():
    store = MemoryStore()
    base = encode({"a": "x" * 2000, "b": "y" * 2000}, store)
    size_before = len(store)
    ext = extend(base["handle"], "c", "z" * 2000, store)
    assert sorted(ext["envelope"]["view"]["branches"].keys()) == ["a", "b", "c"]
    assert len(store) == size_before + 2  # one new leaf c + one new root
    assert store.has(base["handle"])  # prior root survives


def test_extend_last_write_wins():
    store = MemoryStore()
    base = encode({"a": "x" * 2000, "b": "y" * 2000}, store)
    ext = extend(base["handle"], "a", "new", store)
    a_handle = ext["envelope"]["view"]["branches"]["a"]
    assert decode(store.get(a_handle)) == leaf_node("new")


def test_extend_rejects_non_branch_root():
    store = MemoryStore()
    leaf = encode(42, store)  # primitive -> leaf root
    with pytest.raises(WrongKind):
        extend(leaf["handle"], "x", 1, store)


def test_merge_combines_branch_tables_last_write_wins():
    store = MemoryStore()
    m1 = encode({"a": "x" * 2000, "b": "y" * 2000}, store)
    m2 = encode({"b": "Y" * 2000, "c": "z" * 2000}, store)
    merged = merge([m1["handle"], m2["handle"]], store)
    assert sorted(merged["envelope"]["view"]["branches"].keys()) == ["a", "b", "c"]
    m2_node = decode(store.get(m2["handle"]))
    assert is_branch(m2_node)
    assert merged["envelope"]["view"]["branches"]["b"] == m2_node["branches"]["b"]
