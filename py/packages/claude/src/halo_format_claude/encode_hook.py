"""The encode hook — the plumbing. It fires after every qualifying tool returns, encodes the result
into the session store, and replaces what the model sees with the envelope (the map). This is
deterministic and model-independent: the payload is out of context before the model is involved, so
the model cannot leak a full result by forgetting to navigate.

Two passthrough conditions, in order:
  1. The tool IS one of the halo navigation tools. MANDATORY: re-encoding a fetched leaf would
     replace it with a new map and the model would never receive the value. The installer also
     excludes these via the matcher, but this in-hook guard is the load-bearing one.
  2. The result is below the size threshold. Encoding a small result costs a map plus a fetch round
     trip for no benefit, so it passes through untouched.

The hook is async because the SDK requires it; it drives the sync session underneath."""

from .constants import is_halo_nav_tool
from .serialize import parse_tool_output, serialize_envelope, size_of

_DEFAULT_THRESHOLD = 2048


def create_encode_hook(session, threshold: int = _DEFAULT_THRESHOLD):
    """Build the PostToolUse encode hook bound to a session."""

    async def encode_hook(input_data, tool_use_id, context):
        tool_name = input_data.get("tool_name", "")
        if is_halo_nav_tool(tool_name):
            return {}  # never re-encode a fetched leaf
        raw = input_data.get("tool_response")
        if size_of(raw) < threshold:
            return {}

        value = parse_tool_output(raw)
        if value is None:
            return {}

        result = session.ingest(tool_name, input_data.get("tool_input"), value)
        # Describe the fields (kind + bounded preview, read from the store) so the model sees a shape
        # map it can fetch from directly, instead of opaque branch names it has to guess at.
        hints = session.describe(result["envelope"])
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": serialize_envelope(result["envelope"], hints),
            }
        }

    return encode_hook
