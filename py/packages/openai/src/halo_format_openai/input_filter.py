"""The encode plumbing for the OpenAI Agents SDK — a ``call_model_input_filter``.

Unlike the Claude (PostToolUse) and LangGraph (wrap_tool_call) hosts, the OpenAI Agents SDK has **no**
tool-return output-replacement hook: the lifecycle hooks (``on_tool_end``) are observational and return
nothing. The only generic, deterministic seam that catches **every** tool (including external/MCP/hosted
tools you do not own) is ``RunConfig.call_model_input_filter`` — a function that rewrites the assembled
model input *before each model call*. We use it to swap each large tool result for a SHAPE MAP, exactly
as the other adapters swap a ToolMessage's content.

Two consequences of intercepting at input-assembly time rather than tool-return time, both handled here:

1. **The output item carries no tool name.** A ``function_call_output`` item has only ``call_id`` and
   ``output`` — not the tool name or args. So we first index the ``function_call`` items in the same
   input list (``call_id -> {name, arguments}``) and correlate. This is what lets us (a) skip the
   navigation tool's own output — the MANDATORY no-re-encode rule — and (b) feed ``key_of`` the real
   tool name and arguments for entity accumulation.

2. **The filter fires every turn over the whole list, not once per return.** To stay idempotent we keep
   a ``call_id -> shape map`` cache on the filter: the FIRST time a call's output is seen it is ingested
   (assigning a stable map id) and rendered; every later turn reuses the cached string verbatim, so the
   refs the model already saw never shift and a result is never re-encoded into a fresh map. This holds
   whether or not the SDK persists the rewritten list back into history.

The core guarantee is unchanged: the filter runs *before* the model call that would consume the output,
so the raw blob never reaches the model. The store is the envelope's only home on this host (there is no
LangGraph-style artifact channel)."""

from dataclasses import replace as _dc_replace

from .constants import is_halo_nav_tool
from .serialize import parse_tool_output, serialize_envelope, size_of

_DEFAULT_THRESHOLD = 2048

# A shape map starts with this marker; a passthrough guard so an already-encoded output (e.g. a
# persisted map seen by a fresh filter, with no cache entry) is never re-ingested.
_SHAPE_MAP_PREFIX = "[halo] map"


def _get(item, key):
    """Read a field from an input item, which may be a dict (the common TypedDict form) or an object."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _index_calls(items) -> dict:
    """Map ``call_id -> {"name", "args"}`` from the ``function_call`` items in the input list, so an
    output item (which only carries ``call_id``) can be traced back to its tool name and arguments."""
    import json

    calls: dict = {}
    for item in items:
        if _get(item, "type") != "function_call":
            continue
        call_id = _get(item, "call_id")
        if call_id is None:
            continue
        raw_args = _get(item, "arguments")
        args = None
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except (ValueError, TypeError):
                args = raw_args
        else:
            args = raw_args
        calls[call_id] = {"name": _get(item, "name"), "args": args}
    return calls


def _looks_encoded(output) -> bool:
    """True when an output is already a Halo shape map — the no-cache passthrough guard."""
    return isinstance(output, str) and output.lstrip().startswith(_SHAPE_MAP_PREFIX)


def make_input_filter(session, threshold: int = _DEFAULT_THRESHOLD):
    """Build the ``call_model_input_filter`` bound to a session.

    Returns a sync filter ``(CallModelData) -> ModelInputData`` (the core/session stay sync; the SDK
    accepts a sync filter). Holds a per-call_id cache so repeated firings are idempotent."""

    encoded: dict = {}  # call_id -> rendered shape map (stable across turns)

    def filter_model_input(data):
        model_data = data.model_data
        items = model_data.input
        calls = _index_calls(items)

        new_items = list(items)
        changed = False
        for i, item in enumerate(items):
            if _get(item, "type") != "function_call_output":
                continue
            call_id = _get(item, "call_id")
            output = _get(item, "output")

            # Idempotency: a call we already rewrote reuses its cached shape map verbatim.
            if call_id in encoded:
                if output != encoded[call_id]:
                    new_items[i] = {**item, "output": encoded[call_id]} if isinstance(item, dict) else item
                    changed = True
                continue

            call = calls.get(call_id, {})
            name = call.get("name")
            # MANDATORY: never re-encode the navigation tool's own output.
            if name is not None and is_halo_nav_tool(name):
                continue
            if _looks_encoded(output):  # already a shape map (no cache entry) — leave it
                continue
            if size_of(output) < threshold:
                continue
            value = parse_tool_output(output)
            if value is None:
                continue

            result = session.ingest(name, call.get("args"), value)
            shape_map = serialize_envelope(result["envelope"], session.describe(result["envelope"]))
            encoded[call_id] = shape_map
            new_items[i] = {**item, "output": shape_map} if isinstance(item, dict) else item
            changed = True

        if not changed:
            return model_data
        return _dc_replace(model_data, input=new_items)

    return filter_model_input
