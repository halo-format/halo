from halo_format_claude.session import HaloSession

BIG = "x" * 2000  # pads a value past the carve inline threshold so it splits per key


def customer(monthly):
    return {
        "income": {"monthly": monthly, "currency": "USD"},
        "debts": {"monthly": 2604, "currency": "USD"},
        "name": "Jane Smith",
        "notes": BIG,
    }


def test_first_result_is_flat_fields_top_level_no_walk():
    s = HaloSession(now=lambda: "T")
    res = s.ingest("get_customer", {}, customer(4200))
    assert res["id"] == "m1"  # no scalar arg -> synthetic id

    # Flat: the value's own fields are the top-level branches, visible in the envelope (no walk).
    assert sorted(res["envelope"]["view"]["branches"]) == ["debts", "income", "name", "notes"]

    got = s.fetch(["m1.income", "m1.debts"])
    assert got["m1.income"] == {"ok": True, "value": {"monthly": 4200, "currency": "USD"}}
    assert got["m1.debts"] == {"ok": True, "value": {"monthly": 2604, "currency": "USD"}}


def test_source_stamped_without_affecting_content_hash():
    s = HaloSession(now=lambda: "2026-06-03T00:00:00Z")
    a = s.ingest("t", {}, customer(1))  # m1
    b = s.ingest("t", {}, customer(1))  # m2, identical content
    assert a["id"] == "m1"
    assert b["id"] == "m2"
    assert a["envelope"]["root"] == b["envelope"]["root"]  # source is never hashed
    assert a["envelope"]["source"] == {
        "id": "m1",
        "tool": "t",
        "args": {},
        "ts": "2026-06-03T00:00:00Z",
    }


def test_entity_accumulation_folds_shared_arg_calls_into_one_map():
    s = HaloSession()
    first = s.ingest("get_customer", {"id": 7}, customer(5000))
    second = s.ingest(
        "get_appointments",
        {"customerId": 7},
        [{"when": "2026-07-01", "kind": "checkup"}, {"when": "2026-08-01", "kind": "followup"}],
    )
    assert first["id"] == "7"
    assert second["id"] == "7"  # same entity -> same map

    # Two tools accumulate -> namespaced under their (short) names.
    assert sorted(second["envelope"]["view"]["branches"]) == ["get_appointments", "get_customer"]
    customer_branch = s.walk("7.get_customer")
    assert sorted(customer_branch["branches"]) == ["debts", "income", "name", "notes"]

    got = s.fetch(["7.get_appointments", "7.get_customer.income"])
    assert got["7.get_appointments"] == {
        "ok": True,
        "value": [
            {"when": "2026-07-01", "kind": "checkup"},
            {"when": "2026-08-01", "kind": "followup"},
        ],
    }
    assert got["7.get_customer.income"] == {"ok": True, "value": {"monthly": 5000, "currency": "USD"}}


def test_resolves_refs_across_several_maps_in_one_batch():
    s = HaloSession()
    s.ingest("get_customer", {"id": 1}, customer(100))
    s.ingest("get_customer", {"id": 2}, customer(200))
    got = s.fetch(["1.income", "2.income"])  # each map is a single flat result
    assert got["1.income"] == {"ok": True, "value": {"monthly": 100, "currency": "USD"}}
    assert got["2.income"] == {"ok": True, "value": {"monthly": 200, "currency": "USD"}}


def test_fetch_on_a_branch_ref_returns_sub_shape_not_wrongkind():
    # Single batch API, no walk tool: fetching a branch expands to its child refs rather than failing.
    s = HaloSession()
    s.ingest("get_customer", {"id": 7}, customer(5000))
    s.ingest("get_appointments", {"customerId": 7}, [{"when": "2026-07-01"}])

    got = s.fetch(["7.get_customer"])
    entry = got["7.get_customer"]
    assert entry["ok"] is True
    assert entry["kind"] == "branch"
    assert sorted(f["ref"] for f in entry["fields"]) == [
        "7.get_customer.debts",
        "7.get_customer.income",
        "7.get_customer.name",
        "7.get_customer.notes",
    ]


def test_describe_classifies_each_top_level_field_with_a_preview():
    s = HaloSession(now=lambda: "T")
    res = s.ingest("get_customer", {"id": 7}, customer(4200))
    hints = s.describe(res["envelope"])
    income = next(h for h in hints if h["ref"] == "7.income")
    assert income["kind"] == "leaf"
    assert "4200" in income["preview"]
    notes = next(h for h in hints if h["ref"] == "7.notes")
    assert notes["kind"] == "leaf"
    assert notes["shape"].startswith("string[")


def test_before_any_map_fetch_unknown_walk_raises():
    s = HaloSession()
    assert s.fetch(["m1.x"]) == {"m1.x": {"ok": False, "error": "UnknownHandle"}}
    try:
        s.walk("m1.x")
        assert False, "expected walk to raise"
    except RuntimeError:
        pass
