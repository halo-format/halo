"""Unit tests for the stores: content-addressing, idempotent dedup, immutability, missing
handles, batch reads, filesystem persistence, and cross-store handle agreement."""

import re

from halo_format import FileStore, MemoryStore, UnknownHandle

MISSING = "h:" + "0" * 64


def test_memory_put_dedups_identical_bytes():
    s = MemoryStore()
    h1 = s.put(b"hello")
    h2 = s.put(b"hello")
    assert h1 == h2
    assert re.fullmatch(r"h:[0-9a-f]{64}", h1)
    assert len(s) == 1  # stored once


def test_memory_get_and_unknown_handle():
    s = MemoryStore()
    h = s.put(b"x")
    assert s.get(h) == b"x"
    try:
        s.get(MISSING)
        assert False, "expected UnknownHandle"
    except UnknownHandle:
        pass


def test_memory_has():
    s = MemoryStore()
    h = s.put(b"y")
    assert s.has(h) is True
    assert s.has(MISSING) is False


def test_memory_get_many_missing_in_place():
    s = MemoryStore()
    h = s.put(b"present")
    assert s.get_many([h, MISSING]) == [b"present", None]


def test_filestore_roundtrip_and_persistence(tmp_path):
    a = FileStore(str(tmp_path))
    h = a.put(b"persisted")

    b = FileStore(str(tmp_path))  # fresh instance, same dir
    assert b.has(h) is True
    assert b.get(h) == b"persisted"
    try:
        b.get(MISSING)
        assert False, "expected UnknownHandle"
    except UnknownHandle:
        pass
    assert b.get_many([h, MISSING]) == [b"persisted", None]


def test_stores_agree_on_handle(tmp_path):
    data = b"content-addressed regardless of store"
    assert MemoryStore().put(data) == FileStore(str(tmp_path)).put(data)
