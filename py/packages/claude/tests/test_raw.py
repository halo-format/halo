import json

from halo_format_claude.constants import HALO_FETCH_TOOL
from halo_format_claude.raw import HALO_GUIDANCE, create_raw_halo, halo_fetch_tool_def


def _big(n):
    return "x" * n


def test_halo_fetch_tool_def_shape():
    d = halo_fetch_tool_def()
    assert d["name"] == HALO_FETCH_TOOL
    assert len(d["description"]) > 0
    assert d["input_schema"]["type"] == "object"
    assert d["input_schema"]["properties"]["refs"]["type"] == "array"
    assert d["input_schema"]["properties"]["refs"]["items"] == {"type": "string"}
    assert d["input_schema"]["required"] == ["refs"]


def test_create_raw_halo_exposes_bundle():
    halo = create_raw_halo()
    assert halo.tool_def["name"] == HALO_FETCH_TOOL
    assert halo.guidance == HALO_GUIDANCE
    assert halo.session is not None


def test_is_fetch_matches_bare_name():
    halo = create_raw_halo()
    assert halo.is_fetch("halo_fetch") is True
    assert halo.is_fetch("payer_get_claim") is False
    # the raw API tool has no mcp__ prefix (that is the Agent SDK in-process server's form)
    assert halo.is_fetch("mcp__halo__halo_fetch") is False


def test_small_result_passes_through_as_raw_json():
    halo = create_raw_halo()
    value = {"status": "ok", "n": 3}
    out = halo.encode_result("t", {}, value)
    assert out == json.dumps(value)
    assert "[halo]" not in out


def test_large_result_becomes_shape_map_then_fetches_verified():
    halo = create_raw_halo()
    value = {"lines": [1, 2, 3], "bulk": _big(4000)}
    out = halo.encode_result("payer_get_claim", {"claim_id": "CLM-1"}, value)
    assert "[halo]" in out
    assert "CLM-1.lines" in out  # arg_join keys the map on the claim_id argument
    assert _big(4000) not in out  # the bulk stays out of context

    fetched = json.loads(halo.fetch(["CLM-1.lines"]))
    assert fetched["CLM-1.lines"] == {"ok": True, "value": [1, 2, 3]}


def test_custom_threshold():
    halo = create_raw_halo(threshold=10)
    out = halo.encode_result("t", {"id": "m"}, {"a": 1, "b": 2, "c": 3})
    assert "[halo]" in out


def test_shared_session_accumulates():
    a = create_raw_halo()
    b = create_raw_halo(session=a.session)
    assert b.session is a.session
