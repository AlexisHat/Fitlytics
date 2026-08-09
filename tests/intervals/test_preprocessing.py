"""Tests for intervals.preprocessing."""

from datetime import UTC, datetime, timedelta

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.preprocessing import resample_to_1hz
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
