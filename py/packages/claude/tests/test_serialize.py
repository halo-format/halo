import json

from halo_format import MemoryStore
from halo_format import encode as core_encode

from halo_format_claude.serialize import (
    parse_tool_output,
    preview_of,
    serialize_envelope,
    shape_of,
    size_of,
)


def test_size_of_strings_objects_and_nullish():
    assert size_of("abc") == 3
    assert size_of("é") == 2  # 2 UTF-8 bytes
    assert size_of({"a": 1}) == len(json.dumps({"a": 1}).encode("utf-8"))
    assert size_of(None) == 0


def test_size_of_never_raises_on_unserializable():
    cyclic = {}
    cyclic["self"] = cyclic
    assert size_of(cyclic) == 0


def test_parse_tool_output_json_string():
    assert parse_tool_output('{"a":1}') == {"a": 1}
    assert parse_tool_output("[1,2,3]") == [1, 2, 3]


def test_parse_tool_output_keeps_prose():
    assert parse_tool_output("hello world") == "hello world"
    assert parse_tool_output("not json {oops") == "not json {oops"


def test_parse_tool_output_unwraps_mcp_content_block():
    assert parse_tool_output({"content": [{"type": "text", "text": '{"k":2}'}]}) == {"k": 2}
    assert parse_tool_output(
        {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}
    ) == "ab"


def test_parse_tool_output_unwraps_bare_content_block_array():
    # The shape some SDK hosts hand the hook: a bare [{type:text,text}] list.
    assert parse_tool_output([{"type": "text", "text": '{"issue":{"id":"1"},"events":[]}'}]) == {
        "issue": {"id": "1"},
        "events": [],
    }
    # A genuine JSON array (not content blocks) is returned as-is.
    assert parse_tool_output([1, 2, 3]) == [1, 2, 3]


def test_parse_tool_output_passthrough_and_none():
    assert parse_tool_output({"a": [1, 2]}) == {"a": [1, 2]}
    assert parse_tool_output(42) == 42
    assert parse_tool_output(None) is None


def test_shape_of_tags_kind_with_size():
    assert shape_of(1843) == "number"
    assert shape_of(None) == "null"
    assert shape_of(True) == "boolean"
    assert shape_of("checkout-api") == "string[12]"
    assert shape_of([1, 2, 3]) == "array[3]"
    assert shape_of({"a": 1, "b": 2}) == "object{2}"


def test_preview_of_is_bounded_single_line():
    assert preview_of({"id": "BACKEND-12A"}) == '{"id":"BACKEND-12A"}'
    long = preview_of("x" * 500)
    assert len(long) <= 80
    assert long.endswith("…")


def test_serialize_envelope_states_root_kind_and_emits_no_hashes():
    result = core_encode(
        {"income": {"monthly": 4200}, "debts": {"monthly": 2604}, "filler": "x" * 2000},
        MemoryStore(),
    )
    envelope = result["envelope"]
    envelope["source"] = {"id": "m1"}
    out = serialize_envelope(envelope)
    assert "[halo]" in out
    assert '"m1"' in out
    assert "object, 3 fields" in out
    assert "m1.income" in out
    # The hashed envelope and its 64-char handles are not shown to the model.
    assert envelope["root"] not in out
    assert '"halo":"1"' not in out


def test_serialize_envelope_renders_field_hints_when_supplied():
    result = core_encode({"income": {"monthly": 4200}, "filler": "x" * 2000}, MemoryStore())
    envelope = result["envelope"]
    envelope["source"] = {"id": "m1", "tool": "mcp__bank__get_profile"}
    hints = [
        {"ref": "m1.income", "kind": "leaf", "shape": "object{1}", "preview": '{"monthly":4200}'},
        {"ref": "m1.rows", "kind": "branch", "shape": "[branch] array{4}", "preview": "↳ 0, 1, 2, 3"},
    ]
    out = serialize_envelope(envelope, hints)
    assert "from get_profile" in out  # short tool name
    assert 'm1.income  object{1}  {"monthly":4200}' in out
    assert "m1.rows  [branch] array{4}  ↳ 0, 1, 2, 3" in out
