"""Tests for intervals.candidates."""

from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest

from intervals.candidates import _true_runs, find_threshold_candidates
from intervals.config import MEDIUM_SCALE
from intervals.preprocessing import compute_baseline, resample_to_1hz
from intervals.scenarios import clean_5x4min, rolling_terrain_no_intervals
from models import RecordPoint

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(powers: list[int]) -> pl.DataFrame:
    records = [
        RecordPoint(timestamp=START + timedelta(seconds=i), power=p)
        for i, p in enumerate(powers)
    ]
    return compute_baseline(resample_to_1hz(records))


def test_true_runs_of_an_all_false_sequence() -> None:
    assert _true_runs([False, False, False]) == []


def test_true_runs_finds_multiple_separate_runs() -> None:
    assert _true_runs([False, True, True, False, True]) == [(1, 3), (4, 5)]


def test_true_runs_includes_a_run_still_open_at_the_end() -> None:
    assert _true_runs([True, True, False, True]) == [(0, 2), (3, 4)]


def test_find_threshold_candidates_enters_and_exits_a_clear_block() -> None:
    series = _series([100] * 5 + [250] * 10 + [100] * 5)
    assert find_threshold_candidates(series, MEDIUM_SCALE) == [(5, 15)]


def test_find_threshold_candidates_tolerates_a_brief_dip_inside_a_block() -> None:
    # a short dip that stays above the (lower) exit threshold shouldn't split
    series = _series([100] * 5 + [250] * 10 + [180] * 3 + [250] * 10 + [100] * 5)
    candidates = find_threshold_candidates(series, MEDIUM_SCALE)
    assert len(candidates) == 1


def test_find_threshold_candidates_finds_nothing_on_a_flat_ride() -> None:
    series = _series([150] * 60)
    assert find_threshold_candidates(series, MEDIUM_SCALE) == []


def test_find_threshold_candidates_ends_a_block_at_a_recording_gap() -> None:
    # padding on both sides keeps the rolling baseline anchored near 100 W
    # rather than getting pulled toward the blocks' own 250 W
    padding_before = [
        RecordPoint(timestamp=START + timedelta(seconds=i), power=100)
        for i in range(60)
    ]
    block_1 = [
        RecordPoint(timestamp=START + timedelta(seconds=60 + i), power=250)
        for i in range(10)
    ]
    block_2 = [
        RecordPoint(timestamp=START + timedelta(seconds=100 + i), power=250)
        for i in range(10)
    ]
    padding_after = [
        RecordPoint(timestamp=START + timedelta(seconds=110 + i), power=100)
        for i in range(60)
    ]
    records = padding_before + block_1 + block_2 + padding_after
    series = compute_baseline(resample_to_1hz(records))
    candidates = find_threshold_candidates(series, MEDIUM_SCALE)
    # the gap rows (70-99) can never be "in" a block, splitting the run
    assert len(candidates) == 2


def test_find_threshold_candidates_matches_five_blocks_on_the_clean_scenario() -> None:
    records, reference = clean_5x4min()
    series = compute_baseline(resample_to_1hz(records))
    candidates = find_threshold_candidates(series, MEDIUM_SCALE)
    assert len(candidates) == 5

    start = records[0].timestamp
    for (start_index, end_index), ref in zip(candidates, reference, strict=True):
        midpoint = start + timedelta(seconds=(start_index + end_index) / 2)
        assert ref.start <= midpoint <= ref.end


def test_find_threshold_candidates_runs_on_wavy_terrain_without_crashing() -> None:
    # a bare hysteresis pass has no duration/homogeneity notion, so short
    # terrain ripples crossing the threshold are expected here; whether the
    # full pipeline correctly rejects all of them is checked in
    # test_filtering.py against find_candidates(), not this raw step.
    records, _ = rolling_terrain_no_intervals()
    series = compute_baseline(resample_to_1hz(records))
    candidates = find_threshold_candidates(series, MEDIUM_SCALE)
    assert all(start < end for start, end in candidates)


def test_find_threshold_candidates_rejects_empty_series() -> None:
    empty = _series([100]).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        find_threshold_candidates(empty, MEDIUM_SCALE)


def test_find_threshold_candidates_rejects_irregularly_spaced_series() -> None:
    series = _series([100] * 10).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        find_threshold_candidates(series, MEDIUM_SCALE)
