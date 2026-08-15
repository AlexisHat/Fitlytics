"""Tests for analysis.trends."""

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from analysis.trends import rolling_average


def test_rolling_average_of_a_constant_series_is_that_constant() -> None:
    assert rolling_average([5.0] * 7, 3) == [5.0] * 7


def test_rolling_average_shrinks_the_window_at_the_edges() -> None:
    """The first day has no day before it; averaging over what is there
    beats padding the series with invented values."""
    assert rolling_average([1.0, 2.0, 3.0], 3) == [1.5, 2.0, 2.5]


def test_rolling_average_skips_a_missing_day_instead_of_counting_it_as_zero() -> None:
    assert rolling_average([10.0, None, 20.0], 3) == [10.0, 15.0, 20.0]


def test_rolling_average_keeps_a_day_with_no_data_in_its_window_as_none() -> None:
    assert rolling_average([None, None], 1) == [None, None]


def test_rolling_average_with_a_window_of_one_changes_nothing() -> None:
    assert rolling_average([3.0, 9.0, 4.0], 1) == [3.0, 9.0, 4.0]


def test_rolling_average_damps_a_single_outlier() -> None:
    """The point of the trend line: one bad night must not dominate it."""
    smoothed = rolling_average([50.0] * 6 + [200.0] + [50.0] * 6, 7)

    peak = max(value for value in smoothed if value is not None)
    assert peak < 100.0


def test_rolling_average_rejects_a_zero_window() -> None:
    with pytest.raises(deal.PreContractError):
        rolling_average([1.0, 2.0], 0)


def test_rolling_average_rejects_a_negative_window() -> None:
    with pytest.raises(deal.PreContractError):
        rolling_average([1.0, 2.0], -1)


@given(
    values=st.lists(st.floats(min_value=0, max_value=1000), min_size=1, max_size=40),
    window=st.integers(min_value=1, max_value=15),
)
def test_rolling_average_returns_one_value_per_day(
    values: list[float], window: int
) -> None:
    assert len(rolling_average(values, window)) == len(values)


@given(
    values=st.lists(st.floats(min_value=0, max_value=1000), min_size=1, max_size=40),
    window=st.integers(min_value=1, max_value=15),
)
def test_rolling_average_stays_within_the_range_of_its_input(
    values: list[float], window: int
) -> None:
    """Exactly within, not just within tolerance — the implementation
    clamps away polars' running-sum residue, so no smoothed value may
    leave the range even by 1e-14."""
    smoothed = [value for value in rolling_average(values, window) if value is not None]

    assert min(smoothed) >= min(values)
    assert max(smoothed) <= max(values)


def test_rolling_average_never_goes_negative_after_a_large_value_leaves() -> None:
    """polars slides the window over a running sum; a large value leaving
    it does not cancel exactly, which produced -5.7e-14 as the mean of two
    zeros. A physiological measurement must never come out negative."""
    values = [1.7467083215002503, 25.33995710236394, 999.4978408794283, 0.0, 0.0]

    assert rolling_average(values, 3)[-1] == 0.0
