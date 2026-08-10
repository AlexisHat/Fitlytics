"""Tests for intervals.merging."""

import polars as pl

from intervals.config import MEDIUM_SCALE
from intervals.merging import _merge_pass, _should_merge, merge_candidates


def _series(
    powers: list[float], baseline: float = 100.0, standstill_at: set[int] | None = None
) -> pl.DataFrame:
    standstill_at = standstill_at or set()
    return pl.DataFrame(
        {
            "power": powers,
            "baseline_power": [baseline] * len(powers),
            "is_standstill": [i in standstill_at for i in range(len(powers))],
        }
    )


def test_should_merge_a_short_gap_at_or_above_baseline() -> None:
    series = _series([250.0] * 5 + [150.0] * 5 + [250.0] * 5, baseline=100.0)
    assert _should_merge(series, (0, 5), (10, 15), MEDIUM_SCALE) is True


def test_should_not_merge_a_gap_longer_than_the_scale_allows() -> None:
    long_gap = MEDIUM_SCALE.merge_gap_s + 1
    series = _series([250.0] * 5 + [150.0] * long_gap + [250.0] * 5, baseline=100.0)
    assert (
        _should_merge(series, (0, 5), (5 + long_gap, 10 + long_gap), MEDIUM_SCALE)
        is False
    )


def test_should_not_merge_across_a_standstill_in_the_gap() -> None:
    series = _series(
        [250.0] * 5 + [0.0] * 5 + [250.0] * 5, baseline=100.0, standstill_at={7}
    )
    assert _should_merge(series, (0, 5), (10, 15), MEDIUM_SCALE) is False


def test_should_not_merge_across_a_recording_gap() -> None:
    powers: list[float | None] = [250.0] * 5 + [None] * 5 + [250.0] * 5
    series = pl.DataFrame(
        {
            "power": powers,
            "baseline_power": [100.0] * 15,
            "is_standstill": [False] * 15,
        }
    )
    assert _should_merge(series, (0, 5), (10, 15), MEDIUM_SCALE) is False


def test_should_not_merge_when_the_gap_drops_below_baseline() -> None:
    series = _series([250.0] * 5 + [50.0] * 5 + [250.0] * 5, baseline=100.0)
    assert _should_merge(series, (0, 5), (10, 15), MEDIUM_SCALE) is False


def test_should_merge_a_zero_length_gap() -> None:
    series = _series([250.0] * 10, baseline=100.0)
    assert _should_merge(series, (0, 5), (5, 10), MEDIUM_SCALE) is True


def test_merge_pass_collapses_a_chain_in_one_sweep() -> None:
    series = _series([250.0] * 30, baseline=100.0)
    result = _merge_pass(series, [(0, 5), (7, 12), (14, 19), (21, 26)], MEDIUM_SCALE)
    assert result == [(0, 26)]


def test_merge_candidates_on_an_empty_list() -> None:
    series = _series([250.0] * 10, baseline=100.0)
    assert merge_candidates(series, [], MEDIUM_SCALE) == []


def test_merge_candidates_keeps_candidates_separated_by_a_standstill() -> None:
    series = _series(
        [400.0] * 30 + [0.0] * 30 + [400.0] * 30, baseline=100.0, standstill_at={40}
    )
    result = merge_candidates(series, [(0, 30), (60, 90)], MEDIUM_SCALE)
    assert result == [(0, 30), (60, 90)]
