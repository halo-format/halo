import json

from halo_format import MemoryStore
from halo_format import encode as core_encode

from halo_format_claude.serialize import parse_tool_output, serialize_envelope, size_of


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


def test_serialize_envelope_note_then_json():
    result = core_encode(
        {"income": {"monthly": 4200}, "debts": {"monthly": 2604}, "filler": "x" * 2000},
        MemoryStore(),
    )
    envelope = result["envelope"]
    envelope["source"] = {"id": "m1"}
    out = serialize_envelope(envelope)
    note, body = out.split("\n", 1)
    assert "[halo]" in note
    assert '"m1"' in note
    assert "m1.income" in note
    assert json.loads(body) == envelope
