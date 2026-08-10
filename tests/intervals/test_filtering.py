"""Tests for intervals.filtering."""

from datetime import timedelta

import polars as pl

from intervals.config import MEDIUM_SCALE
from intervals.evaluation import Interval, evaluate
from intervals.filtering import (
    _is_clean,
    _meets_elevation,
    _meets_homogeneity,
    _meets_min_duration,
    filter_candidates,
    find_candidates,
)
from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz
from intervals.scenarios import (
    clean_5x4min,
    noisy_5x4min_with_fatigue,
    rolling_terrain_no_intervals,
)


def _series(
    powers: list[float | None],
    baseline: float = 100.0,
    standstill_at: set[int] | None = None,
) -> pl.DataFrame:
    standstill_at = standstill_at or set()
    return pl.DataFrame(
        {
            "power": powers,
            "baseline_power": [baseline] * len(powers),
            "is_standstill": [i in standstill_at for i in range(len(powers))],
        }
    )


def test_meets_min_duration() -> None:
    assert _meets_min_duration((0, MEDIUM_SCALE.min_duration_s), MEDIUM_SCALE) is True
    assert (
        _meets_min_duration((0, MEDIUM_SCALE.min_duration_s - 1), MEDIUM_SCALE) is False
    )


def test_is_clean_rejects_a_candidate_overlapping_a_recording_gap() -> None:
    series = _series([250.0] * 5 + [None] * 5 + [250.0] * 5)
    assert _is_clean(series, (0, 15)) is False


def test_is_clean_rejects_a_candidate_overlapping_a_standstill() -> None:
    series = _series([250.0] * 10, standstill_at={5})
    assert _is_clean(series, (0, 10)) is False


def test_is_clean_accepts_a_candidate_without_gap_or_standstill() -> None:
    series = _series([250.0] * 10)
    assert _is_clean(series, (0, 10)) is True


def test_meets_elevation_accepts_power_well_above_baseline() -> None:
    series = _series([250.0] * 10, baseline=100.0)
    assert _meets_elevation(series, (0, 10)) is True


def test_meets_elevation_rejects_a_small_ripple_above_baseline() -> None:
    series = _series([105.0] * 10, baseline=100.0)
    assert _meets_elevation(series, (0, 10)) is False


def test_meets_homogeneity_accepts_a_steady_block() -> None:
    series = _series([250.0] * 10, baseline=100.0)
    assert _meets_homogeneity(series, (0, 10)) is True


def test_meets_homogeneity_rejects_a_wildly_swinging_block() -> None:
    series = _series([100.0, 400.0] * 5, baseline=100.0)
    assert _meets_homogeneity(series, (0, 10)) is False


def test_filter_candidates_never_grows_the_list() -> None:
    series = _series([250.0] * 10, baseline=100.0)
    result = filter_candidates(series, [(0, 10), (0, 5)], MEDIUM_SCALE)
    assert len(result) <= 2


def test_find_candidates_matches_the_clean_5x4min_scenario_exactly() -> None:
    records, reference = clean_5x4min()
    series = mark_standstill(compute_baseline(resample_to_1hz(records)))
    candidates = find_candidates(series, MEDIUM_SCALE)

    start = records[0].timestamp
    detected = [
        Interval(start + timedelta(seconds=s), start + timedelta(seconds=e))
        for s, e in candidates
    ]
    result = evaluate(reference, detected)
    assert result.true_positives == 5
    assert result.false_positives == 0
    assert result.false_negatives == 0
    assert result.mean_start_offset_s == 0.0
    assert result.mean_end_offset_s == 0.0


def test_find_candidates_on_wavy_terrain_stays_bounded() -> None:
    # tuning territory (M5): the local baseline window can still misjudge a
    # ripple as elevated. Not yet the "null Blöcke" the design document
    # wants, but bounding it here catches a real regression later.
    records, reference = rolling_terrain_no_intervals()
    series = mark_standstill(compute_baseline(resample_to_1hz(records)))
    candidates = find_candidates(series, MEDIUM_SCALE)
    assert reference == []
    assert len(candidates) <= 2


def test_find_candidates_on_the_noisy_fatigue_scenario_still_finds_all_five() -> None:
    records, reference = noisy_5x4min_with_fatigue()
    series = mark_standstill(compute_baseline(resample_to_1hz(records)))
    candidates = find_candidates(series, MEDIUM_SCALE)

    start = records[0].timestamp
    detected = [
        Interval(start + timedelta(seconds=s), start + timedelta(seconds=e))
        for s, e in candidates
    ]
    result = evaluate(reference, detected)
    assert result.true_positives == 5
    assert result.false_positives == 0
    assert result.false_negatives == 0
