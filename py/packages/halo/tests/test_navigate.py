"""Unit tests for the navigator: verified walk/fetch/fetch_many, the trust chain (store-untrusted
safety), ref resolution (raw handle, branch name, nested path, map-scoped via registered
envelopes), and the encode -> open_ -> walk -> fetch round trip that is the L0+L1 milestone."""

import pytest

from halo_format import (
    HashMismatch,
    MemoryStore,
    UnknownHandle,
    WrongKind,
    encode,
    fetch,
    fetch_many,
    open_,
    walk,
)

# Top object > 1024 bytes (via bio) so it carves; profile also carves; score/tags inline as leaves.
DATA = {
    "profile": {"name": "Ada", "city": "London", "bio": "x" * 2000},
    "score": 612,
    "tags": ["a", "b"],
}


def _encoded(value=DATA):
    store = MemoryStore()
    r = encode(value, store)
    return store, r["handle"], r["envelope"]


class TamperStore:
    """Serves correct bytes for everything except one target handle, for which it returns
    attacker-chosen bytes — exercises the store-untrusted guarantee. No get_many, so reads fall
    back to get() and hit this override."""

    def __init__(self, base, target, evil):
        self._base = base
        self._target = target
        self._evil = evil

    def put(self, data):
        return self._base.put(data)

    def get(self, handle):
        return self._evil if handle == self._target else self._base.get(handle)

    def has(self, handle):
        return self._base.has(handle)


def test_open_verifies_honest_branch_root():
    store, _, env = _encoded()
    nav = open_(env, store)
    assert nav.root == env["root"]


def test_open_leaf_root():
    store, _, env = _encoded([1, 2, 3])
    nav = open_(env, store)
    assert nav.root == env["root"]


def test_open_rejects_tampered_view():
    store, _, env = _encoded()
    tampered = {**env, "view": {**env["view"], "summary": "lies"}}
    with pytest.raises(HashMismatch):
        open_(tampered, store)


def test_free_walk_and_fetch_by_handle():
    store, _, env = _encoded()
    profile_handle = env["view"]["branches"]["profile"]
    w = walk(profile_handle, store)
    assert w["summary"] == "3 branches: bio, city, name"
    assert fetch(w["branches"]["name"], store) == "Ada"


def test_walk_on_leaf_and_fetch_on_branch_raise_wrongkind():
    store, _, env = _encoded()
    with pytest.raises(WrongKind):
        walk(env["view"]["branches"]["score"], store)  # leaf
    with pytest.raises(WrongKind):
        fetch(env["view"]["branches"]["profile"], store)  # branch


def test_unknown_handle():
    store, _, _ = _encoded()
    with pytest.raises(UnknownHandle):
        fetch("h:" + "0" * 64, store)


def test_store_untrusted_substituted_leaf_fails():
    store, _, env = _encoded()
    score_handle = env["view"]["branches"]["score"]
    evil = b'{"k":"l","value":999}'
    evil_store = TamperStore(store, score_handle, evil)
    with pytest.raises(HashMismatch):
        fetch(score_handle, evil_store)


def test_navigator_resolves_name_nested_and_raw_handle():
    store, _, env = _encoded()
    nav = open_(env, store)
    assert nav.fetch("score") == 612
    assert nav.fetch("profile.name") == "Ada"
    assert nav.fetch("profile.city") == "London"
    w = nav.walk("profile")
    assert sorted(w["branches"].keys()) == ["bio", "city", "name"]
    assert nav.fetch(env["view"]["branches"]["score"]) == 612  # raw handle


def test_navigator_rejects_leaf_descent_and_unknown_name():
    store, _, env = _encoded()
    nav = open_(env, store)
    with pytest.raises(WrongKind):
        nav.fetch("score.nope")
    with pytest.raises(UnknownHandle):
        nav.fetch("missing")


def test_navigator_map_scoped_refs():
    store = MemoryStore()
    a = encode({"score": 1, "pad": "x" * 2000}, store)
    b = encode({"score": 2, "pad": "y" * 2000}, store)
    env1 = {**a["envelope"], "source": {"id": "m1"}}
    env2 = {**b["envelope"], "source": {"id": "m2"}}
    nav = open_(env1, store).register(env2)
    assert nav.fetch("m1.score") == 1
    assert nav.fetch("m2.score") == 2
    assert nav.fetch("score") == 1  # bare name -> primary (m1)


def test_fetch_many_batches_with_per_ref_results():
    store, _, env = _encoded()
    score_h = env["view"]["branches"]["score"]
    profile_h = env["view"]["branches"]["profile"]
    missing = "h:" + "0" * 64
    out = fetch_many([score_h, profile_h, missing], store)
    assert out[score_h] == {"ok": True, "value": 612}
    assert out[profile_h] == {"ok": False, "error": "WrongKind"}
    assert out[missing] == {"ok": False, "error": "UnknownHandle"}


def test_navigator_fetch_many_surfaces_hashmismatch_per_entry():
    store, _, env = _encoded()
    score_handle = env["view"]["branches"]["score"]
    evil = b'{"k":"l","value":999}'
    evil_nav = open_(env, TamperStore(store, score_handle, evil))
    out = evil_nav.fetch_many(["score", "profile.name", "missing"])
    assert out["score"] == {"ok": False, "error": "HashMismatch"}
    assert out["profile.name"] == {"ok": True, "value": "Ada"}
    assert out["missing"] == {"ok": False, "error": "UnknownHandle"}


def test_round_trip_milestone():
    store, _, env = _encoded()
    nav = open_(env, store)
    out = nav.fetch_many(["profile.name", "profile.city", "score"])
    assert out == {
        "profile.name": {"ok": True, "value": "Ada"},
        "profile.city": {"ok": True, "value": "London"},
        "score": {"ok": True, "value": 612},
    }
