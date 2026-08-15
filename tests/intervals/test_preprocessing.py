"""Tests for intervals.preprocessing."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.config import COASTING_POWER_W
from intervals.preprocessing import (
    effort_threshold,
    mark_standstill,
    resample_to_1hz,
    smooth_power,
)
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _record(
    offset_s: int,
    power: int | None = None,
    heart_rate: int | None = None,
    cadence: int | None = None,
    speed_ms: float | None = None,
    grade_pct: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        power=power,
        heart_rate=heart_rate,
        cadence=cadence,
        speed_ms=speed_ms,
        grade_pct=grade_pct,
    )


def _records_from_powers(
    powers: Sequence[int | None], speeds: Sequence[float | None] | None = None
) -> list[RecordPoint]:
    speeds = speeds if speeds is not None else [None] * len(powers)
    return [
        _record(i, power=power, speed_ms=speed)
        for i, (power, speed) in enumerate(zip(powers, speeds, strict=True))
    ]


def test_resample_materialises_a_gap_as_null_rows() -> None:
    records = [_record(0, power=100), _record(3, power=120)]
    series = resample_to_1hz(records)
    assert series["power"].to_list() == [100, None, None, 120]


def test_resample_keeps_timestamps_one_second_apart() -> None:
    records = [_record(0, power=100), _record(2, power=110)]
    series = resample_to_1hz(records)
    assert series["timestamp"].to_list() == [
        START,
        START + timedelta(seconds=1),
        START + timedelta(seconds=2),
    ]


def test_resample_single_record_yields_one_row() -> None:
    series = resample_to_1hz([_record(0, power=100)])
    assert series["power"].to_list() == [100]


def test_resample_carries_optional_channels() -> None:
    records = [_record(0, heart_rate=140, cadence=90, speed_ms=8.5)]
    series = resample_to_1hz(records)
    assert series["heart_rate"].to_list() == [140]
    assert series["cadence"].to_list() == [90]
    assert series["speed_ms"].to_list() == [8.5]


def test_resample_rejects_empty_list() -> None:
    with pytest.raises(deal.PreContractError):
        resample_to_1hz([])


def test_resample_rejects_unordered_records() -> None:
    with pytest.raises(deal.PreContractError):
        resample_to_1hz([_record(3), _record(0)])


def test_resample_rejects_duplicate_timestamps() -> None:
    with pytest.raises(deal.PreContractError):
        resample_to_1hz([_record(0), _record(0)])


def test_resample_handles_a_value_past_row_100() -> None:
    """Polars' default schema inference only samples the first 100 rows of a
    list-of-dicts; a column that is None throughout that sample and only
    becomes a real float later used to crash the whole DataFrame build."""
    records = [_record(i, power=100) for i in range(120)] + [
        _record(120, power=100, grade_pct=41.4)
    ]

    series = resample_to_1hz(records)

    assert series["power"].to_list()[-1] == 100


@given(gap_s=st.integers(min_value=1, max_value=3600))
def test_resample_row_count_matches_elapsed_seconds(gap_s: int) -> None:
    records = [_record(0, power=100), _record(gap_s, power=100)]
    series = resample_to_1hz(records)
    assert len(series) == gap_s + 1


def test_standstill_marks_run_at_least_min_duration() -> None:
    powers = [200] * 5 + [0] * 20 + [200] * 5
    series = mark_standstill(resample_to_1hz(_records_from_powers(powers)))
    assert series["is_standstill"].to_list() == [False] * 5 + [True] * 20 + [False] * 5


def test_standstill_ignores_run_shorter_than_min_duration() -> None:
    powers = [200] * 5 + [0] * 19 + [200] * 5
    series = mark_standstill(resample_to_1hz(_records_from_powers(powers)))
    assert not any(series["is_standstill"].to_list())


def test_standstill_requires_speed_near_zero_too_when_speed_is_recorded() -> None:
    powers = [0] * 25
    speeds: list[float | None] = [5.0] * 25
    series = mark_standstill(resample_to_1hz(_records_from_powers(powers, speeds)))
    assert not any(series["is_standstill"].to_list())


def test_standstill_falls_back_to_power_only_without_speed_data() -> None:
    series = mark_standstill(resample_to_1hz(_records_from_powers([0] * 25)))
    assert all(series["is_standstill"].to_list())


def test_standstill_never_marks_rows_with_no_power_reading() -> None:
    powers: list[int | None] = [None] * 25
    series = mark_standstill(resample_to_1hz(_records_from_powers(powers)))
    assert not any(series["is_standstill"].to_list())


def test_standstill_rejects_empty_series() -> None:
    empty = resample_to_1hz(_records_from_powers([200])).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        mark_standstill(empty)


def test_standstill_rejects_irregularly_spaced_series() -> None:
    series = resample_to_1hz(_records_from_powers([200] * 10)).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        mark_standstill(series)


def test_smooth_power_leaves_constant_power_unchanged() -> None:
    series = smooth_power(resample_to_1hz(_records_from_powers([200] * 60)))
    assert series["smoothed_power"].to_list() == [200.0] * 60


def test_smooth_power_damps_a_one_second_spike() -> None:
    """The whole point: a single wild second must not reach a threshold on
    its own, or every such second shatters a real effort into fragments."""
    powers = [100] * 60 + [600] + [100] * 60
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))

    assert max(series["smoothed_power"].to_list()) < 200.0


def test_smooth_power_keeps_a_sustained_effort_near_its_real_level() -> None:
    powers = [100] * 120 + [300] * 120 + [100] * 120
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))

    assert series["smoothed_power"].to_list()[180] == 300.0


def test_smooth_power_is_null_without_any_power_data() -> None:
    powers: list[int | None] = [None] * 60
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    assert series["smoothed_power"].null_count() == 60


def test_smooth_power_rejects_empty_series() -> None:
    empty = resample_to_1hz(_records_from_powers([200])).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        smooth_power(empty)


def test_smooth_power_rejects_irregularly_spaced_series() -> None:
    series = resample_to_1hz(_records_from_powers([200] * 10)).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        smooth_power(series)


@given(power=st.integers(min_value=0, max_value=2000))
def test_smooth_power_of_constant_power_is_that_power(power: int) -> None:
    series = smooth_power(resample_to_1hz(_records_from_powers([power] * 40)))
    assert series["smoothed_power"].to_list() == [float(power)] * 40


def test_effort_threshold_separates_two_clear_levels() -> None:
    powers = [100] * 120 + [300] * 120
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    threshold = effort_threshold(series)

    assert threshold is not None
    assert 100 < threshold < 300


def test_effort_threshold_works_when_the_effort_dominates_the_ride() -> None:
    """The reason a ride-global median was rejected: a session that spends
    most of its time working sits above its own median, so a median-derived
    threshold clears nothing at all and detection finds zero blocks."""
    powers = [100] * 60 + [250] * 300
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    threshold = effort_threshold(series)

    assert threshold is not None
    assert 100 < threshold < 250


def test_effort_threshold_ignores_a_long_coasting_stretch() -> None:
    """Coasting is not a third class to split against; without excluding it
    the cut lands between "rolling" and "pedalling" instead of between
    "easy" and "hard"."""
    powers = [0] * 200 + [150] * 120 + [300] * 120
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    threshold = effort_threshold(series)

    assert threshold is not None
    assert 150 < threshold < 300


def test_effort_threshold_is_none_without_any_power_data() -> None:
    powers: list[int | None] = [None] * 60
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    assert effort_threshold(series) is None


def test_effort_threshold_is_none_for_a_ride_spent_entirely_coasting() -> None:
    series = smooth_power(resample_to_1hz(_records_from_powers([0] * 60)))
    assert effort_threshold(series) is None


def test_effort_threshold_is_none_for_perfectly_constant_power() -> None:
    """Nothing to separate: a ride held at one power has no hard class."""
    series = smooth_power(resample_to_1hz(_records_from_powers([180] * 60)))
    assert effort_threshold(series) is None


def test_effort_threshold_rejects_a_series_that_was_never_smoothed() -> None:
    with pytest.raises(deal.PreContractError):
        effort_threshold(resample_to_1hz(_records_from_powers([200] * 60)))


@given(
    easy=st.integers(min_value=COASTING_POWER_W + 1, max_value=200),
    step=st.integers(min_value=50, max_value=400),
)
def test_effort_threshold_lies_between_the_two_levels_it_separates(
    easy: int, step: int
) -> None:
    powers = [easy] * 120 + [easy + step] * 120
    series = smooth_power(resample_to_1hz(_records_from_powers(powers)))
    threshold = effort_threshold(series)

    assert threshold is not None
    assert easy < threshold < easy + step
