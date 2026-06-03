"""Unit tests for behavior the JSON conformance vectors cannot express.

Non-finite numbers are not valid JSON, so they only matter at the encode API boundary; handle
shape and key-order independence are properties of the primitives themselves. The shared
vector-driven conformance lives in py/conformance.
"""

import math
import re

import pytest

from halo_format import canonical, handle_of
from halo_format.errors import CanonicalizationError


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite(bad):
    with pytest.raises(CanonicalizationError):
        canonical(bad)


def test_rejects_non_finite_nested():
    with pytest.raises(CanonicalizationError):
        canonical({"a": 1, "b": [2, math.inf]})


def test_handle_shape():
    assert re.fullmatch(r"h:[0-9a-f]{64}", handle_of({"hello": "world"}))


def test_handle_is_key_order_independent():
    assert handle_of({"a": 1, "b": 2}) == handle_of({"b": 2, "a": 1})
