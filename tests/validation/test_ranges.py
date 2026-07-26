"""Tests for validation.ranges."""

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from validation.ranges import HEART_RATE_BPM, keep_within


def test_keep_within_keeps_value_inside_bounds() -> None:
    assert keep_within(20.0, 240.0, 142) == 142


def test_keep_within_keeps_values_on_both_bounds() -> None:
    assert keep_within(20.0, 240.0, 20) == 20
    assert keep_within(20.0, 240.0, 240) == 240


def test_keep_within_discards_value_above_upper_bound() -> None:
    assert keep_within(20.0, 240.0, 241) is None


def test_keep_within_discards_value_below_lower_bound() -> None:
    assert keep_within(20.0, 240.0, 19) is None


def test_keep_within_passes_missing_value_through() -> None:
    assert keep_within(20.0, 240.0, None) is None


def test_keep_within_rejects_inverted_bounds() -> None:
    with pytest.raises(deal.PreContractError):
        keep_within(240.0, 20.0, 142)


@given(value=st.floats(allow_nan=False, allow_infinity=False))
def test_keep_within_result_is_either_the_input_or_none(value: float) -> None:
    low, high = HEART_RATE_BPM

    result = keep_within(low, high, value)

    assert result is None or (result == value and low <= result <= high)


@given(
    value=st.floats(min_value=20.0, max_value=240.0, allow_nan=False),
)
def test_keep_within_never_discards_a_plausible_heart_rate(value: float) -> None:
    assert keep_within(*HEART_RATE_BPM, value) == value
