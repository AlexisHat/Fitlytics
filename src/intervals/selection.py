"""Choosing the real interval blocks among the merged candidates.

Two things disqualify a merged candidate. It can simply be too short to be
a deliberate effort — ordinary terrain produces plenty of brief rises. Or
it can be far weaker than the session's strongest effort, which is what a
warm-up or a climb on the way to the intervals looks like: repetitions
within one session are ridden at a deliberately similar power, so the reps
cluster near the top and everything else falls away from it.

:func:`find_candidates` ties the whole detection pipeline
(:mod:`intervals.candidates`, :mod:`intervals.merging`, this module)
together into one call.
"""

from itertools import pairwise
from typing import cast

import deal
import polars as pl

from intervals.candidates import find_threshold_candidates
from intervals.config import KEEP_FRACTION, MIN_BLOCK_DURATION_S
from intervals.merging import merge_candidates
from intervals.preprocessing import effort_threshold


def _mean_smoothed_power(series: pl.DataFrame, candidate: tuple[int, int]) -> float:
    """Mean smoothed power within a candidate window.

    Smoothed rather than raw power because a candidate is non-null in that
    column throughout by construction — it was found by thresholding it —
    while raw power may have gaps inside the window.
    """
    start, end = candidate
    return cast(float, series[start:end]["smoothed_power"].mean())


@deal.ensure(lambda _: len(_.result) <= len(_.candidates))
@deal.ensure(
    lambda _: all(end - start >= MIN_BLOCK_DURATION_S for start, end in _.result)
)
def filter_by_duration(candidates: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Discard candidates shorter than ``MIN_BLOCK_DURATION_S``.

    Applied before :func:`select_consistent` so that a brief power spike
    can never become the strongest block the others are measured against.

    Args:
        candidates: Merged ``(start_index, end_index)`` windows, as
            returned by :func:`~intervals.merging.merge_candidates`.

    Returns:
        The subset of ``candidates``, in the same order, lasting at least
        ``MIN_BLOCK_DURATION_S`` seconds.

    >>> filter_by_duration([(0, 60), (100, 400), (500, 700)])
    [(100, 400), (500, 700)]
    """
    return [
        candidate
        for candidate in candidates
        if candidate[1] - candidate[0] >= MIN_BLOCK_DURATION_S
    ]


@deal.ensure(lambda _: len(_.result) <= len(_.candidates))
@deal.ensure(lambda _: len(_.result) > 0 or len(_.candidates) == 0)
def select_consistent(
    series: pl.DataFrame, candidates: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Keep only the candidates ridden near the session's hardest effort.

    Interval repetitions within one session are deliberately ridden at a
    similar power, so they cluster just below the strongest of them. A
    candidate far below that — a warm-up stretch, a climb on the way out —
    is terrain rather than one of the reps. Measured on a real 4x4min
    session this removes exactly the three warm-up candidates around
    140 W while keeping all four repetitions around 250 W.

    The strongest candidate always survives, so a non-empty input never
    yields an empty result.

    Args:
        series: The time series the candidates were found on, with a
            ``smoothed_power`` column.
        candidates: ``(start_index, end_index)`` windows that already
            passed :func:`filter_by_duration`.

    Returns:
        The subset of ``candidates``, in the same order, whose mean
        smoothed power reaches ``KEEP_FRACTION`` of the strongest
        candidate's.

    >>> import polars as pl
    >>> series = pl.DataFrame({"smoothed_power": [100.0] * 5 + [250.0] * 5})
    >>> select_consistent(series, [(0, 5), (5, 10)])
    [(5, 10)]
    """
    if not candidates:
        return []
    powers = [_mean_smoothed_power(series, candidate) for candidate in candidates]
    cutoff = max(powers) * KEEP_FRACTION
    return [
        candidate
        for candidate, power in zip(candidates, powers, strict=True)
        if power >= cutoff
    ]


@deal.pre(lambda series: len(series) > 0)
@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
def find_candidates(series: pl.DataFrame) -> list[tuple[int, int]]:
    """Detect a workout's interval blocks: threshold, merge, select.

    Args:
        series: A 1 Hz-gridded time series with ``power``,
            ``smoothed_power`` and ``is_standstill`` columns, as returned
            by :func:`~intervals.preprocessing.resample_to_1hz`,
            :func:`~intervals.preprocessing.smooth_power` and
            :func:`~intervals.preprocessing.mark_standstill` in sequence;
            must not be empty.

    Returns:
        The detected blocks as ``(start_index, end_index)`` row-index
        pairs into ``series``, chronologically sorted and non-overlapping.
        Empty if the ride has no usable power data at all — a workout
        recorded without a power meter cannot be analysed for intervals.

    Raises:
        deal.PreContractError: If ``series`` is empty.
    """
    threshold_w = effort_threshold(series)
    if threshold_w is None:
        return []
    candidates = find_threshold_candidates(series, threshold_w)
    merged = merge_candidates(series, candidates)
    return select_consistent(series, filter_by_duration(merged))
