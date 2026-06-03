from halo_format_claude.accumulate import arg_join


def test_keys_on_first_scalar_arg_regardless_of_field_name():
    assert arg_join("get_customer", {"id": 123}) == "123"
    assert arg_join("get_appointments", {"customerId": 123}) == "123"
    # Both detail calls about customer 123 land under the same map id, so they fold into one map.


def test_keys_on_value_not_field_name():
    assert arg_join("a", {"customerId": 123}) == arg_join("b", {"id": 123, "extra": "x"})


def test_search_style_call_stays_its_own_map():
    assert arg_join("search", {"query": "smith"}) == "smith"
    assert arg_join("search", {"query": "smith"}) != arg_join("get_customer", {"id": 123})


def test_bare_scalars_and_lists():
    assert arg_join("t", 42) == "42"
    assert arg_join("t", "abc") == "abc"
    assert arg_join("t", [7, 8]) == "7"


def test_none_when_no_id_like_scalar():
    assert arg_join("list_all", {}) is None
    assert arg_join("noop", None) is None
    assert arg_join("t", {"active": True}) is None  # booleans are not id-like
    assert arg_join("t", {"body": "x" * 200}) is None  # long strings are free text
