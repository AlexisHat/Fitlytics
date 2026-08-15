"""Tests for intervals.candidates."""

from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest

from intervals.candidates import _true_runs, find_threshold_candidates
from intervals.preprocessing import resample_to_1hz, smooth_power
from models import RecordPoint

START = datetime(2026, 1, 1, tzinfo=UTC)

SMOOTHING_TOLERANCE_S = 20
"""Smoothing shifts a block's detected edges by up to half its window, so
edge assertions allow that much slack rather than demanding the exact
second."""


def _series(powers: list[int]) -> pl.DataFrame:
    records = [
        RecordPoint(timestamp=START + timedelta(seconds=i), power=p)
        for i, p in enumerate(powers)
    ]
    return smooth_power(resample_to_1hz(records))


def test_true_runs_of_an_all_false_sequence() -> None:
    assert _true_runs([False, False, False]) == []


def test_true_runs_finds_multiple_separate_runs() -> None:
    assert _true_runs([False, True, True, False, True]) == [(1, 3), (4, 5)]


def test_true_runs_includes_a_run_still_open_at_the_end() -> None:
    assert _true_runs([True, True, False, True]) == [(0, 2), (3, 4)]


def test_find_threshold_candidates_finds_one_clear_block() -> None:
    series = _series([100] * 120 + [250] * 240 + [100] * 120)
    candidates = find_threshold_candidates(series, 200.0)

    assert len(candidates) == 1
    start, end = candidates[0]
    assert start == pytest.approx(120, abs=SMOOTHING_TOLERANCE_S)
    assert end == pytest.approx(360, abs=SMOOTHING_TOLERANCE_S)


def test_find_threshold_candidates_finds_nothing_on_a_flat_ride() -> None:
    series = _series([150] * 120)
    assert find_threshold_candidates(series, 200.0) == []


def test_find_threshold_candidates_separates_two_distant_blocks() -> None:
    powers = [100] * 120 + [250] * 180 + [100] * 180 + [250] * 180 + [100] * 120
    candidates = find_threshold_candidates(_series(powers), 200.0)

    assert len(candidates) == 2


def test_find_threshold_candidates_ends_a_block_at_a_recording_gap() -> None:
    """A gap long enough that no real sample falls in its smoothing window
    leaves smoothed power null, which can never be part of a block."""
    before = [
        RecordPoint(timestamp=START + timedelta(seconds=i), power=250)
        for i in range(180)
    ]
    after = [
        RecordPoint(timestamp=START + timedelta(seconds=400 + i), power=250)
        for i in range(180)
    ]
    series = smooth_power(resample_to_1hz(before + after))

    assert len(find_threshold_candidates(series, 200.0)) == 2


def test_find_threshold_candidates_rejects_empty_series() -> None:
    empty = _series([100]).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        find_threshold_candidates(empty, 200.0)


def test_find_threshold_candidates_rejects_irregularly_spaced_series() -> None:
    series = _series([100] * 10).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        find_threshold_candidates(series, 200.0)


@pytest.mark.parametrize("threshold", [0.0, -1.0])
def test_find_threshold_candidates_rejects_a_non_positive_threshold(
    threshold: float,
) -> None:
    with pytest.raises(deal.PreContractError):
        find_threshold_candidates(_series([100] * 60), threshold)
