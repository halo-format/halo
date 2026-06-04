"""HaloSession holds the one piece of shared state in the adapter — the store and the per-entity map
registry — and exposes the three operations the hook and the navigation tools sit on:

    ingest(tool_name, tool_input, value) -> {"envelope", "id"}   (producer; folds into the map)
    walk(ref)                            -> {"summary", "branches"}
    fetch(refs)                          -> verified leaves, per-ref

One entity, one map (SDK architecture, Section 9.1): key_of decides which calls share a map id. A
first call for an id ``encode``s ``{tool: value}``; later calls for the same id ``extend`` that map's
root with a branch named after the tool, so a customer assembled across several endpoints becomes one
growing map rather than several fragments. Because extend reuses unchanged child handles and retains
the prior root, each entity map also carries its own version history for free.

The session is SYNC — it sits on the sync Python core (matching the port convention). Only the thin
SDK-facing wrappers (the async hook and tool handlers) are async, as the SDK requires.

Every read is verified by the core Navigator, so the store stays untrusted. The Navigator resolves
map-scoped refs (``m1.income``, ``123.get_appointments``) against the registered envelopes; raw
handles always work without registration."""

from datetime import datetime, timezone
from typing import Optional

from halo_format import (
    HashMismatch,
    MemoryStore,
    Navigator,
    WrongKind,
    branch_node,
    build_envelope,
    decode,
    derive_summary,
    hash_bytes,
    is_branch,
    is_leaf,
    serialize,
)
from halo_format import encode as _encode

from .accumulate import KeyOf, arg_join
from .serialize import preview_of, shape_of

_MAX_CHILD_NAMES = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _branch_name(tool_name: str) -> str:
    """A short branch label for an accumulated tool: strip the ``mcp__<server>__`` prefix."""
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) == 3:
            return parts[2]
    return tool_name


class HaloSession:
    def __init__(self, store=None, key_of: Optional[KeyOf] = None, alg: str = "sha256", now=None):
        self.store = store if store is not None else MemoryStore()
        self._key_of = key_of or arg_join
        self._alg = alg
        self._now = now or _now_iso
        self._maps: dict[str, dict] = {}  # id -> latest envelope, for ref resolution + accumulation
        # id -> {branch_name: subtree_root_handle}: the per-tool trees folded into each entity map.
        self._entity_tools: dict[str, dict[str, str]] = {}
        self._navigator: Optional[Navigator] = None  # seeded by the first map, extended via register
        self._synthetic = 0

    def ingest(self, tool_name: str, tool_input, value) -> dict:
        """Encode a tool result into the store and return its envelope and map id.

        A map's FIRST result is encoded flat — the value's own fields become the top-level branches,
        so the model sees them in the envelope and can batch-fetch leaves with no extra walk. Only
        when a SECOND tool result accumulates into the same entity map (per key_of) do we namespace
        each tool's tree under its (short) name, since then the field names would otherwise collide.
        """
        map_id = self._key_of(tool_name, tool_input)
        if map_id is None:
            self._synthetic += 1
            map_id = f"m{self._synthetic}"

        # Encode the value's own tree once; reuse its root as this tool's subtree under the entity.
        sub = _encode(value, self.store, alg=self._alg)
        tools = self._entity_tools.setdefault(map_id, {})
        tools[_branch_name(tool_name)] = sub["handle"]

        if len(tools) == 1:
            # Single result: the map IS the value's tree — fields are top-level, no walk needed.
            envelope = sub["envelope"]
        else:
            # Accumulation: namespace each tool's tree under its name (reusing every subtree handle;
            # only the new root node is stored).
            branches = dict(tools)
            root = self.store.put(serialize(branch_node(derive_summary(None, branches), branches)))
            envelope = build_envelope(root, decode(self.store.get(root)), self._alg)

        # source identifies the map and traces it to the call; it is envelope-only and never hashed.
        envelope["source"] = {
            "id": map_id,
            "tool": tool_name,
            "args": tool_input,
            "ts": self._now(),
        }
        self._maps[map_id] = envelope
        self._register(envelope)
        return {"envelope": envelope, "id": map_id}

    def _register(self, envelope: dict) -> None:
        if self._navigator is not None:
            self._navigator.register(envelope)
        else:
            self._navigator = Navigator(envelope, self.store)

    def walk(self, ref: str) -> dict:
        """Verified walk of a branch ref (raw handle or ``mapId.branch[.child]``). Internal — not a tool."""
        if self._navigator is None:
            raise RuntimeError("no halo maps in this session yet")
        return self._navigator.walk(ref)

    def fetch(self, refs) -> dict:
        """Verified batch fetch — the single navigation surface. Leaves return their value; a ref that
        lands on a branch returns the branch's sub-shape instead of a WrongKind error, so one tool
        covers both pulling and expanding. One bad ref never sinks the others (per-ref ok/error)."""
        if self._navigator is None:
            return {ref: {"ok": False, "error": "UnknownHandle"} for ref in refs}
        # The core batch verifies every leaf in one pass; branch refs come back WrongKind, which we
        # turn into a sub-shape expansion below rather than surfacing as an error.
        base = self._navigator.fetch_many(refs)
        out: dict = {}
        for ref in refs:
            res = base[ref]
            if res["ok"]:
                out[ref] = {"ok": True, "value": res["value"]}
            elif res.get("error") == "WrongKind":
                try:
                    out[ref] = self._expand(ref)
                except Exception:
                    out[ref] = res
            else:
                out[ref] = res
        return out

    def describe(self, envelope: dict) -> list:
        """Describe an envelope's top-level fields for the shape map the model sees: one hint dict per
        branch, classified (leaf vs branch) and previewed by reading each child node. Sorted by ref so
        the listing order is deterministic (matching the structural summary's sorted names)."""
        map_id = (envelope.get("source") or {}).get("id", "")
        hints = []
        for name, handle in envelope["view"]["branches"].items():
            ref = f"{map_id}.{name}" if map_id else name
            try:
                hints.append(self._hint_for(ref, handle))
            except Exception:
                hints.append({"ref": ref, "kind": "leaf", "shape": "?"})
        hints.sort(key=lambda h: h["ref"])
        return hints

    def _expand(self, ref: str) -> dict:
        """Expand a branch ref into a fetch entry carrying its child refs + hints (the in-fetch
        fallback so a mis-fetched branch self-corrects in the same call instead of dead-ending)."""
        handle = self._navigator.resolve(ref)
        node = self._read(handle)
        if not is_branch(node):
            raise WrongKind(f"expand expects a branch: {ref}")
        fields = [self._hint_for(f"{ref}.{name}", h) for name, h in node["branches"].items()]
        fields.sort(key=lambda h: h["ref"])
        return {
            "ok": True,
            "kind": "branch",
            "note": "This ref is a branch, not a value. halo_fetch the leaf refs below to read it.",
            "fields": fields,
        }

    def _hint_for(self, ref: str, handle: str) -> dict:
        """Classify one child handle into a hint dict: a leaf gets its shape + a bounded value preview;
        a branch gets a ``[branch]`` shape and its child names as the preview (one level, bounded)."""
        node = self._read(handle)
        if is_leaf(node):
            value = node["value"]
            return {"ref": ref, "kind": "leaf", "shape": shape_of(value), "preview": preview_of(value)}
        child_names = list(node["branches"])
        array_like = len(child_names) > 0 and all(n.isdigit() for n in child_names)
        shape = f"[branch] {'array' if array_like else 'object'}{{{len(child_names)}}}"
        shown = ", ".join(child_names[:_MAX_CHILD_NAMES])
        more = ", …" if len(child_names) > _MAX_CHILD_NAMES else ""
        return {"ref": ref, "kind": "branch", "shape": shape, "preview": f"↳ {shown}{more}"}

    def _read(self, handle: str) -> dict:
        """A verified read of a handle from the store: re-hash the bytes under the bound alg before
        decode, so the shape map can never describe substituted bytes. Same check the Navigator makes."""
        data = self.store.get(handle)
        if hash_bytes(data, self._alg) != handle:
            raise HashMismatch(handle)
        return decode(data)
