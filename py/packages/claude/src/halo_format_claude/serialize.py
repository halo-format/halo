"""Serialization at the SDK boundary: measure a raw tool result, parse it into a JSON value the
core can encode, and serialize a halo envelope back into the string the model sees.

updatedToolOutput carries the tool's visible output, so the envelope is emitted as a compact JSON
string prefixed with a one-line note that tells the model this is a navigable map and how to address
it. The branches in view.branches are reached with refs of the form ``<mapId>.<branch>``."""

import json

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


def serialize_envelope(envelope: dict) -> str:
    """Serialize an envelope into the string the model receives in place of the blob: a one-line note
    naming the map and how to address it, then the compact envelope JSON."""
    map_id = (envelope.get("source") or {}).get("id", "?")
    refs = ", ".join(f"{map_id}.{b}" for b in envelope["view"]["branches"])
    note = (
        f'[halo] Large result stored out of context as map "{map_id}". '
        "Read view.summary, then halo_fetch the refs you need"
        + (f" (e.g. {refs})" if refs else "")
        + "; halo_walk a branch to see its sub-structure. Map:"
    )
    return f"{note}\n{json.dumps(envelope, separators=(',', ':'))}"
