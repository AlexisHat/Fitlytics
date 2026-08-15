"""Candidate search: one threshold on the smoothed power signal.

A stretch counts as a candidate block for as long as smoothed power stays
above a threshold derived from the ride's own reference level. The earlier
implementation needed two thresholds (a higher one to enter a block, a
lower one to stay in it) because it ran on raw 1 Hz power, which crosses
any single threshold constantly. Smoothing removes that chatter upstream,
so one threshold is enough here.
"""

from itertools import pairwise

import deal
import polars as pl

from intervals.preprocessing import is_1hz_spaced


def _true_runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Start/end index pairs of the maximal True-runs in a boolean sequence.

    >>> _true_runs([False, True, True, False, True])
    [(1, 3), (4, 5)]
    """
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


@deal.pre(lambda series, threshold_w: len(series) > 0)
@deal.pre(lambda series, threshold_w: is_1hz_spaced(series))
@deal.pre(lambda series, threshold_w: threshold_w > 0)
@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
def find_threshold_candidates(
    series: pl.DataFrame, threshold_w: float
) -> list[tuple[int, int]]:
    """Find candidate block windows as the runs above a power threshold.

    Args:
        series: A 1 Hz-gridded time series with a ``smoothed_power``
            column, as returned by
            :func:`~intervals.preprocessing.smooth_power`; must not be
            empty.
        threshold_w: The power, in watts, a second must reach to count as
            part of an effort; must be positive.

    Returns:
        Candidate windows as ``(start_index, end_index)`` row-index pairs
        into ``series``, chronologically sorted and non-overlapping. A row
        with no smoothed power (a recording gap long enough that its whole
        window is empty, or a ride with no power meter) can never be "in" a
        block and ends one already open.

    Raises:
        deal.PreContractError: If ``series`` is empty, not spaced exactly
            one second apart, or ``threshold_w`` is not positive.

    >>> from datetime import UTC, datetime, timedelta
    >>> import polars as pl
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(20)],
    ...         "smoothed_power": [100.0] * 5 + [250.0] * 10 + [100.0] * 5,
    ...     }
    ... )
    >>> find_threshold_candidates(series, 200.0)
    [(5, 15)]
    """
    flags = [
        power is not None and power >= threshold_w
        for power in series["smoothed_power"].to_list()
    ]
    return _true_runs(flags)
