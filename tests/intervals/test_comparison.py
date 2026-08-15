"""Tests for intervals.comparison."""

from datetime import UTC, datetime, timedelta

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.blocks import IntervalBlock
from intervals.comparison import compare_to_plan
from models import PlannedIntervalSpec

START = datetime(2026, 1, 1, tzinfo=UTC)


def _block(duration_minutes: float, avg_power_w: float) -> IntervalBlock:
    duration = timedelta(minutes=duration_minutes)
    return IntervalBlock(
        start=START,
        end=START + duration,
        duration=duration,
        avg_power_w=avg_power_w,
        avg_power_relative_to_ftp=None,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=1.0,
    )


def _plan(
    repetitions: int = 4, duration_minutes: float = 4, target_power_w: int = 250
) -> PlannedIntervalSpec:
    return PlannedIntervalSpec(
        repetitions=repetitions,
        duration=timedelta(minutes=duration_minutes),
        target_power_w=target_power_w,
    )


def test_compare_reports_one_entry_per_detected_block() -> None:
    blocks = [_block(4, 250.0), _block(4, 240.0), _block(4, 245.0)]

    comparison = compare_to_plan(blocks, _plan())

    assert comparison.detected_repetitions == 3
    assert len(comparison.repetitions) == 3


def test_compare_keeps_the_planned_count_even_when_fewer_were_ridden() -> None:
    comparison = compare_to_plan([_block(4, 250.0)], _plan(repetitions=4))

    assert comparison.planned_repetitions == 4
    assert comparison.detected_repetitions == 1


def test_compare_reports_extra_repetitions_rather_than_trimming_them() -> None:
    """An effort beyond the plan is information about the ride, not an
    error to be hidden so the counts line up."""
    blocks = [_block(4, 250.0)] * 5

    comparison = compare_to_plan(blocks, _plan(repetitions=4))

    assert comparison.detected_repetitions == 5
    assert len(comparison.repetitions) == 5


def test_compare_reports_a_repetition_ridden_short_as_negative() -> None:
    comparison = compare_to_plan([_block(3, 250.0)], _plan(duration_minutes=4))

    assert comparison.repetitions[0].duration_deviation == timedelta(minutes=-1)


def test_compare_reports_a_repetition_ridden_long_as_positive() -> None:
    comparison = compare_to_plan([_block(5, 250.0)], _plan(duration_minutes=4))

    assert comparison.repetitions[0].duration_deviation == timedelta(minutes=1)


def test_compare_reports_missing_the_power_target_as_negative() -> None:
    comparison = compare_to_plan([_block(4, 230.0)], _plan(target_power_w=250))

    assert comparison.repetitions[0].power_deviation_w == -20.0


def test_compare_averages_the_power_deviation_across_repetitions() -> None:
    blocks = [_block(4, 260.0), _block(4, 240.0)]

    comparison = compare_to_plan(blocks, _plan(target_power_w=250))

    assert comparison.mean_power_deviation_w == 0.0


def test_compare_carries_the_ridden_values_through_unchanged() -> None:
    comparison = compare_to_plan([_block(4.5, 263.0)], _plan())

    assert comparison.repetitions[0].duration == timedelta(minutes=4.5)
    assert comparison.repetitions[0].avg_power_w == 263.0


def test_compare_rejects_an_empty_block_list() -> None:
    """Averaging a deviation over nothing has no meaning; the caller must
    handle "nothing detected" before asking for a comparison."""
    with pytest.raises(deal.PreContractError):
        compare_to_plan([], _plan())


@given(
    powers=st.lists(st.floats(min_value=0, max_value=2000), min_size=1, max_size=10),
    target=st.integers(min_value=1, max_value=1000),
)
def test_mean_power_deviation_lies_between_the_smallest_and_largest(
    powers: list[float], target: int
) -> None:
    blocks = [_block(4, power) for power in powers]

    comparison = compare_to_plan(blocks, _plan(target_power_w=target))

    deviations = [repetition.power_deviation_w for repetition in comparison.repetitions]
    assert min(deviations) <= comparison.mean_power_deviation_w <= max(deviations)
