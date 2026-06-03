"""open_(envelope, store) -> Navigator(walk, fetch, fetch_many, root), plus the free
walk/fetch/fetch_many low-level path.

Every read verifies: read bytes, recompute the hash under the bound alg, compare to the requested
handle, and only then decode. That single check is what makes the store untrusted — substituted or
corrupted bytes fail at the moment they are read, before their contents are used, and the guarantee
propagates from the verified root down every branch to every leaf (the trust chain).

walk returns a branch's summary + child handles (never leaf data); fetch returns one verified leaf;
fetch_many verifies several in one call with per-ref results, so one unknown or tampered entry never
sinks the batch. The Navigator additionally resolves map-scoped refs (e.g. m1.income, or income /
income.monthly against the opened envelope) to handles before verifying; raw handles always work and
need no registration.

Sync to match the Python Store (see store.py's note on the async divergence from TypeScript).
"""

from .envelope import verify_envelope
from .errors import HaloError, HashMismatch, UnknownHandle, WrongKind
from .hash import hash_bytes
from .node import decode, is_branch, is_leaf


def _is_raw_handle(ref):
    return ref.startswith("h:")


def _read_verified(handle, store, alg):
    """Read a handle's bytes and verify them against it before decoding. The load-bearing check."""
    data = store.get(handle)  # raises UnknownHandle if absent
    if hash_bytes(data, alg) != handle:
        raise HashMismatch(handle)
    return decode(data)


def _get_many_bytes(store, handles):
    get_many = getattr(store, "get_many", None)
    if get_many is not None:
        return get_many(handles)
    out = []
    for h in handles:
        try:
            out.append(store.get(h))
        except UnknownHandle:
            out.append(None)
    return out


def walk(handle, store, alg="sha256"):
    """Verified walk of a branch handle: returns its summary and child handles, never leaf data."""
    node = _read_verified(handle, store, alg)
    if not is_branch(node):
        raise WrongKind(f"walk expects a branch: {handle}")
    return {"summary": node["summary"], "branches": node["branches"]}


def fetch(handle, store, alg="sha256"):
    """Verified fetch of a leaf handle: returns its value."""
    node = _read_verified(handle, store, alg)
    if not is_leaf(node):
        raise WrongKind(f"fetch expects a leaf: {handle}")
    return node["value"]


def _verify_batch(present, store, alg):
    """Verify already-resolved (ref, handle) pairs independently. One backend round trip via
    get_many. Missing -> UnknownHandle, bad hash -> HashMismatch, branch-where-leaf -> WrongKind."""
    out = {}
    byteses = _get_many_bytes(store, [h for _, h in present])
    for (ref, handle), data in zip(present, byteses):
        if data is None:
            out[ref] = {"ok": False, "error": "UnknownHandle"}
        elif hash_bytes(data, alg) != handle:
            out[ref] = {"ok": False, "error": "HashMismatch"}
        else:
            node = decode(data)
            out[ref] = (
                {"ok": True, "value": node["value"]}
                if is_leaf(node)
                else {"ok": False, "error": "WrongKind"}
            )
    return out


def fetch_many(refs, store, alg="sha256"):
    """Verified batch fetch over raw handles (low-level path; each ref is treated as a handle)."""
    return _verify_batch([(r, r) for r in refs], store, alg)


class Navigator:
    """Bound to an envelope's algorithm, store, and root. Resolves map-scoped refs and verifies
    every read. Register additional envelopes (by their source.id) to resolve refs across several
    maps in one session, e.g. m1.income vs m2.income."""

    def __init__(self, primary, store):
        self._primary = primary
        self._store = store
        self._alg = primary["alg"]
        self.root = primary["root"]
        self._registry = {}
        self._register(primary)

    def _register(self, env):
        src = env.get("source")
        if src and src.get("id"):
            self._registry[src["id"]] = env

    def register(self, env):
        """Register another envelope so its mapId.branch refs resolve in this session."""
        self._register(env)
        return self

    def resolve(self, ref):
        """Resolve a ref (raw handle, mapId.branch[.child...], or a path on the opened envelope)."""
        if _is_raw_handle(ref):
            return ref
        parts = ref.split(".")
        if len(parts) >= 2 and parts[0] in self._registry:
            env = self._registry[parts[0]]
            return self._resolve_path(env["view"]["branches"], parts[1:], ref)
        return self._resolve_path(self._primary["view"]["branches"], parts, ref)

    def _resolve_path(self, branches, segs, ref):
        if not segs:
            raise UnknownHandle(f"empty ref: {ref}")
        handle = branches.get(segs[0])
        if handle is None:
            raise UnknownHandle(f"unknown ref: {ref}")
        for seg in segs[1:]:
            node = _read_verified(handle, self._store, self._alg)
            if not is_branch(node):
                raise WrongKind(f"ref descends into a leaf: {ref}")
            handle = node["branches"].get(seg)
            if handle is None:
                raise UnknownHandle(f"unknown ref: {ref}")
        return handle

    def walk(self, ref):
        return walk(self.resolve(ref), self._store, self._alg)

    def fetch(self, ref):
        return fetch(self.resolve(ref), self._store, self._alg)

    def fetch_many(self, refs):
        present = []
        out = {}
        for r in refs:
            try:
                present.append((r, self.resolve(r)))
            except HaloError as e:
                # A resolution failure is surfaced per-entry (by error class name), never raised.
                out[r] = {"ok": False, "error": type(e).__name__}
        out.update(_verify_batch(present, self._store, self._alg))
        return out


def open_(envelope, store):
    """Open an envelope into a Navigator, verifying the root. Zero fetches for an honest branch root."""
    alg = envelope["alg"]
    # The inlined view lets us verify a branch root with no store read (verify_envelope re-hashes
    # the reconstructed root node and compares to the claimed root handle).
    if not verify_envelope(envelope):
        # Either a leaf root (value not inlined) or a tampered branch view. Read the real root to
        # tell them apart: a branch here means the view was tampered.
        node = _read_verified(envelope["root"], store, alg)
        if is_branch(node):
            raise HashMismatch(f"envelope view does not match root: {envelope['root']}")
        # leaf root: nothing branch-navigable; a later fetch(root) re-verifies it.
    return Navigator(envelope, store)
