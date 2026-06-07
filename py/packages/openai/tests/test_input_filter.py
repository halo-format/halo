"""The call_model_input_filter: it rewrites a large function_call_output into a shape map, correlates
each output to its function_call (by call_id) to get the tool name/args, excludes the navigation tool's
own output (the mandatory no-re-encode rule), passes small/already-encoded results through, and — because
it fires every turn over the whole list — stays idempotent across repeated firings via a per-call_id
cache."""

from types import SimpleNamespace

from agents.run_config import CallModelData, ModelInputData

from halo_format_openai import HaloSession, make_input_filter

BIG = '{"profile":{"income":{"monthly":4200},"debts":{"monthly":2604}},"filler":"' + "x" * 3000 + '"}'


def _call(call_id, name, arguments):
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": arguments}


def _output(call_id, output):
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def _data(items):
    # The filter only reads data.model_data; agent/context are irrelevant here.
    return CallModelData(
        model_data=ModelInputData(input=items, instructions=None), agent=None, context=None
    )


def _run(filt, items):
    return filt(_data(items)).input


def _filt(threshold=2048):
    session = HaloSession(now=lambda: "T")
    return make_input_filter(session, threshold), session


def _output_of(items, call_id):
    for it in items:
        if it.get("type") == "function_call_output" and it.get("call_id") == call_id:
            return it["output"]
    raise AssertionError("no output for " + call_id)


def test_large_output_becomes_shape_map():
    filt, session = _filt()
    items = [_call("c1", "bureau", '{"applicant":99}'), _output("c1", BIG)]
    out = _run(filt, items)

    rewritten = _output_of(out, "c1")
    assert rewritten.startswith('[halo] map "99"')  # arg_join keyed on applicant=99, via the call item
    # the full payload is reachable from the store, not in the rewritten output
    assert session.fetch(["99.profile"])["99.profile"]["ok"] is True


def test_call_item_left_intact():
    # Only the output item is rewritten; the function_call item is untouched.
    filt, _ = _filt()
    call = _call("c1", "bureau", '{"applicant":99}')
    out = _run(filt, [call, _output("c1", BIG)])
    assert out[0] == call


def test_nav_tool_output_excluded():
    # MANDATORY: halo_fetch's own output, correlated by call_id, must never be re-encoded.
    filt, _ = _filt()
    items = [_call("c1", "halo_fetch", '{"refs":["x"]}'), _output("c1", BIG)]
    out = _run(filt, items)
    assert _output_of(out, "c1") == BIG  # untouched


def test_small_output_passes_through():
    filt, _ = _filt()
    items = [_call("c1", "ping", "{}"), _output("c1", '{"ok":true}')]
    out = _run(filt, items)
    assert _output_of(out, "c1") == '{"ok":true}'


def test_unchanged_input_returns_same_model_data():
    # Nothing to encode -> the original ModelInputData is returned (no needless copy).
    filt, _ = _filt()
    data = _data([_call("c1", "ping", "{}"), _output("c1", "{}")])
    assert filt(data) is data.model_data


def test_idempotent_across_repeated_firings_for_synthetic_id():
    # The sharp case: a no-id-arg tool gets a synthetic map id (m1). Without the per-call_id cache, a
    # second firing would re-ingest and assign m2, shifting refs the model already saw. The cache keeps
    # it m1 and never re-ingests.
    filt, session = _filt()
    items = [_call("c1", "list_logs", "{}"), _output("c1", BIG)]

    first = _output_of(_run(filt, items), "c1")
    assert first.startswith('[halo] map "m1"')

    # Re-run the filter on the ORIGINAL items (the no-persistence case): same string, no new map.
    second = _output_of(_run(filt, [_call("c1", "list_logs", "{}"), _output("c1", BIG)]), "c1")
    assert second == first
    assert session._synthetic == 1  # m2 was never minted


def test_already_encoded_shape_map_passes_through_without_cache():
    # A persisted shape map seen by a fresh filter (no cache entry) is left alone — the prefix guard.
    filt, _ = _filt()
    shape_map = '[halo] map "m1" — object, 2 fields, stored out of context. ...'
    out = _run(filt, [_call("c1", "list_logs", "{}"), _output("c1", shape_map)])
    assert _output_of(out, "c1") == shape_map


def test_persisted_rewrite_is_stable():
    # If the SDK persists the rewrite, the next turn sees the shape map already in `output`; the cache
    # hit means it stays identical (and small, so even without the cache it would pass the threshold).
    filt, _ = _filt()
    items = [_call("c1", "bureau", '{"applicant":99}'), _output("c1", BIG)]
    out1 = _run(filt, items)
    persisted = [_call("c1", "bureau", '{"applicant":99}'), _output("c1", _output_of(out1, "c1"))]
    out2 = _run(filt, persisted)
    assert _output_of(out2, "c1") == _output_of(out1, "c1")


def test_entity_accumulation_folds_shared_id_calls():
    # Two calls sharing arg value 123 fold into one growing map (the second namespaced under its tool).
    filt, session = _filt()
    a = '{"id":123,"a":"' + "x" * 3000 + '"}'
    b = '{"id":123,"b":"' + "y" * 3000 + '"}'
    _run(filt, [_call("c1", "get_customer", '{"id":123}'), _output("c1", a)])
    out = _run(filt, [_call("c2", "get_appointments", '{"id":123}'), _output("c2", b)])
    rewritten = _output_of(out, "c2")
    assert rewritten.startswith('[halo] map "123"')
    # accumulation namespaces each tool's tree under its name
    assert "get_customer" in rewritten and "get_appointments" in rewritten


def test_output_as_content_block_list_is_unwrapped():
    # An output delivered as MCP-style content blocks is unwrapped and encoded, not treated as opaque.
    filt, session = _filt()
    blocks = [{"type": "text", "text": BIG}]
    out = _run(filt, [_call("c1", "bureau", '{"applicant":99}'), _output("c1", blocks)])
    assert _output_of(out, "c1").startswith('[halo] map "99"')
    assert session.fetch(["99.profile"])["99.profile"]["ok"] is True
