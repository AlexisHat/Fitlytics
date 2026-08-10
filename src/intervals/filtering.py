"""Filtering implausible candidates, and the single-scale pipeline entry point.

The last step of Schritt 2 (candidate search): a threshold-found, merged
window can still be too short, too close to baseline to be a real effort,
overlapping a gap or standstill, or too internally erratic to be a
deliberate block rather than wavy terrain. :func:`find_candidates` ties the
whole scale-local pipeline (:mod:`intervals.candidates`,
:mod:`intervals.merging`, this module) together into one call.
"""

from typing import cast

import deal
import polars as pl

from intervals.candidates import find_threshold_candidates
from intervals.config import (
    MAX_HOMOGENEITY_CV,
    MIN_ELEVATION_ABOVE_BASELINE_FRACTION,
    Scale,
)
from intervals.merging import merge_candidates


def _meets_min_duration(candidate: tuple[int, int], scale: Scale) -> bool:
    """Whether a candidate is at least as long as this scale requires."""
    start, end = candidate
    return end - start >= scale.min_duration_s


def _is_clean(series: pl.DataFrame, candidate: tuple[int, int]) -> bool:
    """Whether a candidate overlaps no recording gap and no standstill.

    Both are hard block boundaries by design (see
    ``docs/entscheidungen.md``), so a candidate spanning either is an
    artefact of the earlier steps, not a real block.
    """
    start, end = candidate
    block = series[start:end]
    return block["power"].null_count() == 0 and not bool(block["is_standstill"].any())


def _meets_elevation(series: pl.DataFrame, candidate: tuple[int, int]) -> bool:
    """Whether a candidate's mean power clears the local baseline by enough.

    Enough to count as a real effort rather than a ripple in the base pace.
    """
    start, end = candidate
    block = series[start:end]
    mean_power = block["power"].mean()
    mean_baseline = block["baseline_power"].mean()
    if mean_power is None or mean_baseline is None:
        return False
    return cast(float, mean_power) >= cast(float, mean_baseline) * (
        1 + MIN_ELEVATION_ABOVE_BASELINE_FRACTION
    )


def _meets_homogeneity(series: pl.DataFrame, candidate: tuple[int, int]) -> bool:
    """Whether a candidate's power is steady enough to be deliberate.

    A block that swings wildly internally is more likely wavy terrain than
    a deliberate, steady effort.
    """
    start, end = candidate
    power = series[start:end]["power"]
    mean_power = power.mean()
    std_power = power.std()
    if not mean_power:
        return False
    coefficient_of_variation = cast(float, std_power) / cast(float, mean_power)
    return coefficient_of_variation <= MAX_HOMOGENEITY_CV


@deal.ensure(lambda _: len(_.result) <= len(_.candidates))
def filter_candidates(
    series: pl.DataFrame, candidates: list[tuple[int, int]], scale: Scale
) -> list[tuple[int, int]]:
    """Discard candidates that fail any of the single-scale filters.

    Args:
        series: The time series the candidates were found on, with
            ``power``, ``baseline_power`` and ``is_standstill`` columns.
        candidates: Merged ``(start_index, end_index)`` windows, as
            returned by :func:`~intervals.merging.merge_candidates`.
        scale: The time scale's tuning parameters.

    Returns:
        The subset of ``candidates`` (in the same order) that meet the
        minimum duration, clear the baseline by enough, don't overlap a
        gap or standstill, and are internally homogeneous enough.
    """
    return [
        candidate
        for candidate in candidates
        if _meets_min_duration(candidate, scale)
        and _is_clean(series, candidate)
        and _meets_elevation(series, candidate)
        and _meets_homogeneity(series, candidate)
    ]


@deal.pre(lambda series, scale: len(series) > 0)
def find_candidates(series: pl.DataFrame, scale: Scale) -> list[tuple[int, int]]:
    """Find this scale's interval blocks: threshold, merge, filter.

    Args:
        series: A 1 Hz-gridded time series with ``power``,
            ``baseline_power`` and ``is_standstill`` columns, as returned
            by :func:`~intervals.preprocessing.resample_to_1hz`,
            :func:`~intervals.preprocessing.compute_baseline` and
            :func:`~intervals.preprocessing.mark_standstill` in sequence;
            must not be empty.
        scale: The time scale's tuning parameters.

    Returns:
        The scale's surviving candidate blocks as ``(start_index,
        end_index)`` row-index pairs into ``series``, chronologically
        sorted and non-overlapping.
    """
    threshold_candidates = find_threshold_candidates(series, scale)
    merged = merge_candidates(series, threshold_candidates, scale)
    return filter_candidates(series, merged, scale)
