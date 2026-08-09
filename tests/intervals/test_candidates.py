"""Tests for intervals.candidates."""

from datetime import UTC, datetime, timedelta

import deal
import numpy as np
import polars as pl
import pytest

from intervals.candidates import (
    _cusum,
    _pair_edges,
    _smooth_power,
    find_rough_candidates,
)
from intervals.config import MEDIUM_SCALE
from intervals.preprocessing import compute_baseline, resample_to_1hz
from intervals.scenarios import clean_5x4min
from models import RecordPoint

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(powers: list[int]) -> pl.DataFrame:
    records = [
        RecordPoint(timestamp=START + timedelta(seconds=i), power=p)
        for i, p in enumerate(powers)
    ]
    return compute_baseline(resample_to_1hz(records))


def test_smooth_power_of_a_constant_signal_is_unchanged() -> None:
    series = _series([150] * 30)
    smoothed = _smooth_power(series, MEDIUM_SCALE)
    assert smoothed.to_list() == [150.0] * 30


def test_cusum_rises_above_baseline_and_falls_below_it() -> None:
    smoothed = pl.Series([200.0, 200.0, 200.0])
    baseline = pl.Series([150.0, 150.0, 150.0])
    result = _cusum(smoothed, baseline)
    assert result.tolist() == [50.0, 100.0, 150.0]


def test_cusum_treats_missing_values_as_at_baseline() -> None:
    smoothed = pl.Series([200.0, None, 200.0])
    baseline = pl.Series([150.0, 150.0, 150.0])
    result = _cusum(smoothed, baseline)
    assert result.tolist() == [50.0, 50.0, 100.0]


def test_pair_edges_of_a_flat_signal_finds_nothing() -> None:
    cusum = np.zeros(50)
    assert _pair_edges(cusum, MEDIUM_SCALE) == []


def test_pair_edges_closes_a_block_still_rising_at_the_last_sample() -> None:
    # falls to a dip, then keeps rising to the very last sample - no cool-down
    cusum = np.array([0, -3, -8, -3, 6, 16, 26, 36, 46], dtype=float)
    scale = MEDIUM_SCALE._replace(prominence_ws=5.0)
    assert _pair_edges(cusum, scale) == [(2, 8)]


def test_pair_edges_rejects_non_positive_prominence() -> None:
    with pytest.raises(deal.PreContractError):
        _pair_edges(np.zeros(10), MEDIUM_SCALE._replace(prominence_ws=0.0))


def test_find_rough_candidates_finds_five_on_the_clean_scenario() -> None:
    records, reference = clean_5x4min()
    series = compute_baseline(resample_to_1hz(records))
    candidates = find_rough_candidates(series, MEDIUM_SCALE)
    assert len(candidates) == 5

    start = records[0].timestamp
    for (start_index, end_index), ref in zip(candidates, reference, strict=True):
        midpoint = start + timedelta(seconds=(start_index + end_index) / 2)
        assert ref.start <= midpoint <= ref.end


def test_find_rough_candidates_rejects_empty_series() -> None:
    empty = _series([100]).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        find_rough_candidates(empty, MEDIUM_SCALE)


def test_find_rough_candidates_rejects_irregularly_spaced_series() -> None:
    series = _series([100] * 10).filter(
        pl.col("timestamp") != START + timedelta(seconds=3)
    )
    with pytest.raises(deal.PreContractError):
        find_rough_candidates(series, MEDIUM_SCALE)
