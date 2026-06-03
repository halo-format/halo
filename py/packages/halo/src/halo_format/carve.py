"""carve(value, path) -> {"as": "leaf"} | {"as": "branch", "children": {...}, "summary"?: str}.

auto_carve default: split a non-empty object into one branch per key; chunk arrays longer than a
threshold (default 25) into contiguous slices; inline everything below a small byte threshold as a
leaf. Hosts/skills override with task knowledge — an explicit carve always wins over the default.
Bounds node size so no single node need be the whole payload. Pure and deterministic: the carve
shape is part of what gets hashed.
"""

from .canonical import canonical_bytes

DEFAULT_ARRAY_THRESHOLD = 25
DEFAULT_INLINE_BYTES = 1024


def make_auto_carve(array_threshold=DEFAULT_ARRAY_THRESHOLD, inline_bytes=DEFAULT_INLINE_BYTES):
    """Build an auto_carve policy with custom thresholds. `auto_carve` is this with the defaults."""

    def auto_carve(value, path):
        # bool is a dict/list-free primitive in Python, so it falls through to leaf below.
        if isinstance(value, dict):
            if not value:
                return {"as": "leaf"}  # {} is a terminal leaf, not a branch
            if len(canonical_bytes(value)) <= inline_bytes:
                return {"as": "leaf"}  # small object inlines whole
            return {"as": "branch", "children": dict(value)}
        if isinstance(value, list):
            if len(value) <= array_threshold:
                return {"as": "leaf"}  # short array inlines as one leaf
            children = {}
            chunks = (len(value) + array_threshold - 1) // array_threshold
            for i in range(chunks):
                children[str(i)] = value[i * array_threshold : (i + 1) * array_threshold]
            return {"as": "branch", "children": children}  # each chunk re-carves to a leaf
        return {"as": "leaf"}  # primitives (None, bool, number, str) are always leaves

    return auto_carve


# The default carve policy: object-by-key, chunk long arrays, inline small subtrees.
auto_carve = make_auto_carve()
