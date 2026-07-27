"""Tests for analysis.metrics."""

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from analysis import average
from analysis.metrics import _is_between


def test_average_of_three_values() -> None:
    assert average([140, 150, 160]) == 150.0


def test_average_of_single_value() -> None:
    assert average([142]) == 142.0


def test_average_rejects_empty_list() -> None:
    with pytest.raises(deal.PreContractError):
        average([])


@given(
    values=st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), min_size=1
    )
)
def test_average_is_always_between_min_and_max(values: list[float]) -> None:
    result = average(values)

    assert _is_between(result, min(values), max(values))
