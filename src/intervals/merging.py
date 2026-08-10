"""Merging nearby candidates of the same time scale into single blocks.

A real interval effort often shows up as several separate CUSUM rises —
a brief signal dropout, a driver's momentary easing, or sensor noise can
all split what is really one continuous block. This step recombines
candidates that are close enough, with nothing disqualifying between them.
"""

from itertools import pairwise
from typing import cast

import deal
import polars as pl

from intervals.config import Scale


def _should_merge(
    series: pl.DataFrame, first: tuple[int, int], second: tuple[int, int], scale: Scale
) -> bool:
    """Whether two chronologically consecutive candidates should merge.

    Args:
        series: The time series the candidates were found on, with
            ``power``, ``baseline_power`` and ``is_standstill`` columns.
        first: The earlier candidate.
        second: The later candidate.
        scale: The time scale's tuning parameters.

    Returns:
        True if the gap between the candidates is short enough, contains
        no standstill or recording gap, and its mean power doesn't fall
        below baseline.
    """
    gap_start, gap_end = first[1], second[0]
    if gap_end - gap_start > scale.merge_gap_s:
        return False

    gap = series[gap_start:gap_end]
    if len(gap) == 0:
        return True
    if gap["is_standstill"].any():
        return False
    if gap["power"].null_count() > 0:
        return False

    # .mean() is typed as a broad union across all polars dtypes; power and
    # baseline_power are both Float64 columns, so the result is always a
    # plain float (or None for an all-null gap, handled above the cast).
    mean_deviation = (gap["power"] - gap["baseline_power"]).mean()
    return mean_deviation is not None and cast(float, mean_deviation) >= 0


def _merge_pass(
    series: pl.DataFrame, candidates: list[tuple[int, int]], scale: Scale
) -> list[tuple[int, int]]:
    """One left-to-right sweep, merging each candidate where it qualifies.

    Each candidate is compared against the last *kept* (possibly already
    merged) one, so a chain of three or more mergeable candidates collapses
    within this single sweep.
    """
    if not candidates:
        return []
    merged = [candidates[0]]
    for candidate in candidates[1:]:
        if _should_merge(series, merged[-1], candidate, scale):
            merged[-1] = (merged[-1][0], candidate[1])
        else:
            merged.append(candidate)
    return merged


@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
def merge_candidates(
    series: pl.DataFrame, candidates: list[tuple[int, int]], scale: Scale
) -> list[tuple[int, int]]:
    """Repeatedly merge nearby candidates until no more merges apply.

    A single left-to-right sweep already resolves chains (a merged
    candidate is immediately compared to what follows), but merging
    repeatedly until the result stops changing keeps this correct even if
    the merge rule above changes in a way that no longer has that property.

    Args:
        series: The time series the candidates were found on, with
            ``power``, ``baseline_power`` and ``is_standstill`` columns.
        candidates: Refined ``(start_index, end_index)`` windows, as
            returned by :func:`~intervals.candidates.refine_candidates`.
        scale: The time scale's tuning parameters.

    Returns:
        The merged candidates, chronologically sorted and non-overlapping.

    >>> import polars as pl
    >>> series = pl.DataFrame(
    ...     {
    ...         "power": [250.0] * 5 + [200.0] * 5 + [250.0] * 5,
    ...         "baseline_power": [100.0] * 15,
    ...         "is_standstill": [False] * 15,
    ...     }
    ... )
    >>> from intervals.config import MEDIUM_SCALE
    >>> merge_candidates(series, [(0, 5), (10, 15)], MEDIUM_SCALE)
    [(0, 15)]
    """
    current = sorted(candidates)
    while True:
        merged = _merge_pass(series, current, scale)
        if merged == current:
            return merged
        current = merged
