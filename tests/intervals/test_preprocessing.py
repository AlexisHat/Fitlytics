"""Tests for intervals.preprocessing."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _record(
    offset_s: int,
    power: int | None = None,
    heart_rate: int | None = None,
    cadence: int | None = None,
    speed_ms: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        power=power,
        heart_rate=heart_rate,
        cadence=cadence,
        speed_ms=speed_ms,
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


def test_baseline_is_constant_for_constant_power() -> None:
    series = compute_baseline(resample_to_1hz(_records_from_powers([150] * 30)))
    assert series["baseline_power"].to_list() == [150.0] * 30


def test_baseline_tracks_local_drift_not_a_single_global_median() -> None:
    powers = [100] * 700 + [300] * 700
    series = compute_baseline(resample_to_1hz(_records_from_powers(powers)))
    baseline = series["baseline_power"].to_list()
    assert baseline[350] == 100.0
    assert baseline[1050] == 300.0


def test_baseline_skips_null_power_within_the_window() -> None:
    powers: list[int | None] = [100] * 10 + [None] * 5 + [100] * 10
    series = compute_baseline(resample_to_1hz(_records_from_powers(powers)))
    assert series["baseline_power"].to_list() == [100.0] * 25


def test_baseline_is_null_without_any_power_data() -> None:
    powers: list[int | None] = [None] * 30
    series = compute_baseline(resample_to_1hz(_records_from_powers(powers)))
    assert series["baseline_power"].null_count() == 30


def test_baseline_rejects_empty_series() -> None:
    empty = resample_to_1hz(_records_from_powers([200])).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        compute_baseline(empty)


def test_baseline_rejects_irregularly_spaced_series() -> None:
    series = resample_to_1hz(_records_from_powers([200] * 10)).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        compute_baseline(series)
