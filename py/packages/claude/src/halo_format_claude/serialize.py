"""Serialization at the SDK boundary: measure a raw tool result, parse it into a JSON value the
core can encode, and serialize a halo envelope back into the string the model sees.

updatedToolOutput carries the tool's visible output. What the model sees in place of the blob is a
SHAPE MAP, not the raw envelope: the root kind stated up front, then one line per field giving its
ref, its kind (leaf vs ``[branch]``), and a bounded preview. This is deliberately not the hashed
envelope JSON — the 64-char branch handles are dead weight to the model (it navigates by
``<mapId>.<field>`` refs, which the session's navigator resolves from its own registry), and showing
only names without kinds is exactly what made the model guess the root kind and fetch a branch as if
it were a leaf. The hints close both gaps. The envelope object itself is unchanged and still held
verbatim in the session for verified reads."""

import json

# A per-field descriptor (a plain dict ``{"ref", "kind", "shape", "preview"}``) the model sees in the
# shape map. ``shape`` is a short structural tag ("number", "string[42]", "object{4}",
# "[branch] object{7}"); ``preview`` is a bounded sample of a leaf's value, or a branch's child names.
# Built by HaloSession.describe (it needs the store to read each child node); rendered here.

_PREVIEW_MAX = 80

# A tool's raw output is a string, an already-parsed value, or the MCP content-block shape
# ``{"content": [{"type": "text", "text": ...}]}``.


def size_of(raw) -> int:
    """Byte length of a raw tool output, used for the size threshold. Never raises."""
    if raw is None:
        return 0
    if isinstance(raw, str):
        return len(raw.encode("utf-8"))
    try:
        return len(json.dumps(raw).encode("utf-8"))
    except (TypeError, ValueError):
        return 0  # unserializable (e.g. a cycle) — treat as below threshold, pass through


def parse_tool_output(raw):
    """Coerce a raw tool output into a JSON value to encode.

    Strings are parsed as JSON when they look like it and otherwise kept as a string leaf; the MCP
    ``{"content": [{"text": ...}]}`` block is unwrapped to its concatenated text (parsed when it is
    itself JSON). Anything already-structured is returned as is. Returns ``None`` when there is
    nothing meaningful to encode.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return _parse_maybe_json(raw)
    # The MCP result may arrive as {"content": [{type:text,text}]} OR as the bare content-block list
    # [{type:text,text}] (the shape some SDK hosts hand the hook). Unwrap either.
    if isinstance(raw, (dict, list)):
        text = _extract_content_text(raw)
        if text is not None:
            return _parse_maybe_json(text)
        return raw
    return raw  # int | float | bool


def _parse_maybe_json(s: str):
    trimmed = s.strip()
    if trimmed == "":
        return s
    # Only attempt a parse on something that looks like JSON, so plain prose stays a string leaf.
    if trimmed[0] in "{[\"":
        try:
            return json.loads(trimmed)
        except (json.JSONDecodeError, ValueError):
            return s
    return s


def _extract_content_text(value):
    """Unwrap the MCP content-block shape to its text, concatenating text blocks.

    Accepts both the ``{"content": [...]}`` dict and a bare ``[{type:text,text}]`` list. Returns None
    when the value is not content blocks (a genuine list/dict result), so it is encoded as-is.
    """
    if isinstance(value, list):
        content = value
    elif isinstance(value, dict) and isinstance(value.get("content"), list):
        content = value["content"]
    else:
        return None
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "".join(texts) if texts else None


def shape_of(value) -> str:
    """A short structural tag for a leaf value: its kind plus a size for strings/lists/objects."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return f"string[{len(value)}]"
    if isinstance(value, list):
        return f"array[{len(value)}]"
    return f"object{{{len(value)}}}"


def preview_of(value, max_len: int = _PREVIEW_MAX) -> str:
    """A bounded, single-line JSON sample of a value — enough to recognise it, never the whole payload."""
    try:
        s = json.dumps(value, separators=(",", ":"))
    except (TypeError, ValueError):
        return ""
    return s if len(s) <= max_len else f"{s[: max_len - 1]}…"


def _is_scalar_shape(shape: str) -> bool:
    return shape in ("null", "boolean", "number")


def _hint_line(hint: dict) -> str:
    """One field line: ref, structural tag, then the preview/child-names."""
    preview = hint.get("preview")
    if preview:
        eq = "= " if hint["kind"] == "leaf" and _is_scalar_shape(hint["shape"]) else ""
        tail = f"  {eq}{preview}"
    else:
        tail = ""
    return f'  {hint["ref"]}  {hint["shape"]}{tail}'


def _root_shape(names) -> str:
    """``object, 7 fields`` / ``array, 4 chunks`` for a branch root."""
    n = len(names)
    array_like = n > 0 and all(name.isdigit() for name in names)
    if array_like:
        return f"array, {n} chunks"
    return f"object, {n} field{'' if n == 1 else 's'}"


def _short_tool(tool: str) -> str:
    if tool.startswith("mcp__"):
        parts = tool.split("__", 2)
        if len(parts) == 3:
            return parts[2]
    return tool


def serialize_envelope(envelope: dict, hints=None) -> str:
    """Serialize an envelope into the string the model receives in place of the blob: the map id and
    root kind stated up front, then (when ``hints`` are supplied) one line per field with its kind and
    a bounded preview. With no hints it degrades to a bare ref list — still no hashes, still names the
    root kind, just without the per-field previews the session computes from the store."""
    source = envelope.get("source") or {}
    map_id = source.get("id", "?")
    names = list(envelope["view"]["branches"])
    is_leaf_root = len(names) == 0
    if is_leaf_root:
        root = envelope["view"]["summary"]
        if root.startswith("leaf:"):
            root = root[len("leaf:"):].strip()
    else:
        root = _root_shape(names)
    from_ = f" from {_short_tool(source['tool'])}" if source.get("tool") else ""

    head = (
        f'[halo] map "{map_id}" — {root}{from_}, stored out of context. '
        "Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; "
        "each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other "
        "ref returns its value."
    )

    if is_leaf_root:
        return f'{head}\nFetch "{map_id}" itself to read the value.'

    if hints:
        lines = [_hint_line(h) for h in hints]
    else:
        lines = [f"  {map_id}.{n}" for n in names]
    return f"{head}\nFields:\n" + "\n".join(lines)
