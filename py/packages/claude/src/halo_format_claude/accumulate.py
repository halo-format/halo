"""Entity accumulation policy: which calls fold into one growing map (SDK architecture, Section 9.1).

key_of(tool_name, tool_input) returns an entity key, or None to give the call its own fresh map. The
default, arg_join, keys on the first scalar argument value, so normalized REST detail calls about one
entity group together: get_customer({"id": 123}) and get_appointments({"customer_id": 123}) both key
on 123 and fold into one map, while search({"query": "smith"}) keys on "smith" and stays its own list
map until the first detail call. It keys on the argument VALUE, not the field name or any result id,
which is what lets a list result land under the entity instead of fragmenting.

arg_join's one real gap is value collision across entity types (customer 123 vs invoice 123, both
passing 123). That is the single thing a generic heuristic cannot resolve alone; supply a domain
key_of (e.g. one that prefixes the resource type) when it matters, as it usually does for money or
medical data."""

from typing import Callable, Optional

KeyOf = Callable[[str, object], Optional[str]]

# A short scalar (number, or string up to this many chars) is treated as an id-like argument worth
# grouping on. Longer strings are typically free text (a query, a body) and are skipped.
_MAX_KEY_STRING_LENGTH = 128


def _scalar_key(value) -> Optional[str]:
    # bool is an int subclass in Python; exclude it explicitly (a flag is not an id).
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and 0 < len(value) <= _MAX_KEY_STRING_LENGTH:
        return value
    return None


def arg_join(tool_name: str, tool_input: object) -> Optional[str]:
    """Default policy: group by the first scalar argument value.

    Dicts are scanned in insertion order, lists in index order; a bare scalar input is its own key.
    Returns None when no scalar argument is present (e.g. a no-arg call), so that call gets a fresh
    synthetic map id.
    """
    direct = _scalar_key(tool_input)
    if direct is not None:
        return direct
    if isinstance(tool_input, dict):
        for value in tool_input.values():
            k = _scalar_key(value)
            if k is not None:
                return k
    elif isinstance(tool_input, (list, tuple)):
        for item in tool_input:
            k = _scalar_key(item)
            if k is not None:
                return k
    return None
