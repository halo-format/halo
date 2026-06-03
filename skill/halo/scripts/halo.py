"""Bundled helper for the Halo skill (code-execution path only), Python agents.

Re-exports the halo_format core surface — encode / walk / fetch / fetch_many — bound to a default
in-process store, so a skill-loaded agent gets the light deployment with nothing to configure. Each
encoded result is registered under a session map id (m1, m2, ...), so branches are addressable by
readable ref (e.g. ``m1.income``) while the long handle stays the verification key. Every read
verifies; a HashMismatch means the data was altered and must not be trusted.

Same best-effort caveat as halo.ts: this only fires if the model routes data through code. Prefer a
deterministic host adapter where one exists, and let the skill be guidance only.
"""

from halo_format import MemoryStore, Navigator
from halo_format import encode as _core_encode

_store = MemoryStore()
_navigator: Navigator | None = None
_n = 0


def encode(value):
    """Encode a result into the default store and return its halo {"handle", "envelope"}."""
    global _navigator, _n
    result = _core_encode(value, _store)
    _n += 1
    result["envelope"]["source"] = {"id": f"m{_n}"}  # session map id, so `m1.income` refs resolve
    if _navigator is None:
        _navigator = Navigator(result["envelope"], _store)
    else:
        _navigator.register(result["envelope"])
    return result


def _nav():
    if _navigator is None:
        raise RuntimeError("encode a result before navigating")
    return _navigator


def walk(ref):
    """Expand a branch ref to its summary and child refs, without pulling leaf data."""
    return _nav().walk(ref)


def fetch(ref):
    """Fetch a single leaf ref, verified on read."""
    return _nav().fetch(ref)


def fetch_many(refs):
    """Fetch several leaf refs in one call, verified per-ref.

    Prefer this over single fetches: each call is a round trip, so gather every ref a step needs and
    pull them together. One bad entry (e.g. a HashMismatch) is surfaced for that ref and never sinks
    the batch.
    """
    return _nav().fetch_many(refs)


__all__ = ["encode", "walk", "fetch", "fetch_many", "MemoryStore", "Navigator"]
