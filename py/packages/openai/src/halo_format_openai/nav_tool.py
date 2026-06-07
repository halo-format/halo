"""The navigation surface — how the model pulls back what the input filter withheld. A single OpenAI
Agents SDK ``function_tool``, ``halo_fetch``, backed by the session store and verified on read. No MCP
server: it is an ordinary function tool, appended to the agent's tools list and bound to the model like
any other.

One tool on purpose: an earlier design (in the Claude adapter's history) also exposed halo_walk and the
model wasted turns choosing between them and fetching a branch ref through the leaf tool. halo_fetch now
does both — a leaf ref returns its value, a branch ref returns its sub-shape — so there is a single
batch API and nothing to disambiguate.

halo_fetch takes a LIST of refs: each fetch is a separate model round trip, the dominant latency in the
loop, so the model is nudged to gather every ref a step needs and pull them in one call. It returns a
per-ref result (JSON), so one unknown or tampered entry (surfaced as a HashMismatch) never sinks the
batch.

The pure helper (``halo_fetch``) is split from the tool wrapping so it can be tested without the SDK.

NOTE on the exclusion: this tool's output must never be re-encoded by the input filter (that would
replace a fetched leaf with a new map). The filter enforces that by correlating each
``function_call_output`` back to its ``function_call`` and skipping anything named ``halo_fetch`` — see
``input_filter.py``. The tool keeps the canonical name from ``constants.HALO_FETCH_TOOL`` so the
exclusion can never drift from the registration."""

import json

from agents import function_tool

from .constants import HALO_FETCH_TOOL


def halo_fetch(session, refs) -> dict:
    """Fetch several refs at once, verified, with a per-ref result; branch refs return their sub-shape."""
    return session.fetch(refs)


_FETCH_DESC = (
    "The one tool for reading a halo map. Pass ALL the refs a step needs in one call (refs is a list) "
    "rather than one at a time — each call is a separate round trip. A ref like `m1.income` (or a raw "
    "`h:` handle) that points at a value returns it as {ok:true,value}; a ref that points at a "
    "[branch] returns {ok:true,kind:'branch',fields:[…]} listing its sub-refs to fetch next. An entry "
    "with ok=false (e.g. HashMismatch) means that data must not be trusted."
)


def create_halo_fetch_tool(session):
    """Build the single ``halo_fetch`` function tool over the given session.

    The schema (``refs: array<string>``) is derived from the type hint by ``function_tool``; the
    handler returns the per-ref results as a JSON string, which becomes the tool's ``output``."""

    @function_tool(name_override=HALO_FETCH_TOOL, description_override=_FETCH_DESC)
    def _halo_fetch(refs: list[str]) -> str:
        return json.dumps(halo_fetch(session, refs))

    return _halo_fetch
