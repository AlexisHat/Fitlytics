"""Merging nearby candidates into single blocks.

One real effort rarely stays above the threshold without interruption: a
momentary ease-off, a corner, or a short signal dropout all split it into
several candidates. Measured on real rides, a single 8 s dip and a 26 s one
were enough to cut two plainly continuous efforts into pieces. This step
recombines candidates that are close enough, with nothing disqualifying
between them.
"""

from itertools import pairwise

import deal
import polars as pl

from intervals.config import MERGE_GAP_S


def _should_merge(
    series: pl.DataFrame, first: tuple[int, int], second: tuple[int, int]
) -> bool:
    """Whether two chronologically consecutive candidates should merge.

    Args:
        series: The time series the candidates were found on, with
            ``power`` and ``is_standstill`` columns.
        first: The earlier candidate.
        second: The later candidate.

    Returns:
        True if the gap between the candidates is short enough and
        contains neither a standstill nor a recording gap — both are hard
        block boundaries by design, so an effort never spans one.
    """
    gap_start, gap_end = first[1], second[0]
    if gap_end - gap_start > MERGE_GAP_S:
        return False

    gap = series[gap_start:gap_end]
    if len(gap) == 0:
        return True
    return not bool(gap["is_standstill"].any()) and gap["power"].null_count() == 0


def _merge_pass(
    series: pl.DataFrame, candidates: list[tuple[int, int]]
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
        if _should_merge(series, merged[-1], candidate):
            merged[-1] = (merged[-1][0], candidate[1])
        else:
            merged.append(candidate)
    return merged


@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
@deal.ensure(lambda _: len(_.result) <= len(_.candidates))
def merge_candidates(
    series: pl.DataFrame, candidates: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Repeatedly merge nearby candidates until no more merges apply.

    A single left-to-right sweep already resolves chains (a merged
    candidate is immediately compared to what follows), but merging
    repeatedly until the result stops changing keeps this correct even if
    the merge rule above changes in a way that no longer has that property.

    Args:
        series: The time series the candidates were found on, with
            ``power`` and ``is_standstill`` columns.
        candidates: ``(start_index, end_index)`` windows, as returned by
            :func:`~intervals.candidates.find_threshold_candidates`.

    Returns:
        The merged candidates, chronologically sorted and non-overlapping.

    >>> import polars as pl
    >>> series = pl.DataFrame(
    ...     {
    ...         "power": [250.0] * 5 + [200.0] * 5 + [250.0] * 5,
    ...         "is_standstill": [False] * 15,
    ...     }
    ... )
    >>> merge_candidates(series, [(0, 5), (10, 15)])
    [(0, 15)]
    """
    current = sorted(candidates)
    while True:
        merged = _merge_pass(series, current)
        if merged == current:
            return merged
        current = merged
