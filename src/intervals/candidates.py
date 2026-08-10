"""Single-scale candidate search: a hysteresis threshold on raw power.

A stretch counts as a candidate block once power rises far enough above
the local baseline ("entered") and keeps counting until it drops back
close to baseline again ("exited") — the same idea as
:func:`~intervals.preprocessing.mark_standstill`, just for "clearly above
baseline" instead of "near zero". Using two thresholds instead of one
means a brief dip inside a block doesn't immediately end it.
"""

from itertools import pairwise

import deal
import polars as pl

from intervals.config import (
    HYSTERESIS_ENTRY_FRACTION,
    HYSTERESIS_EXIT_FRACTION,
    HYSTERESIS_MARGIN_W,
    Scale,
)
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


@deal.pre(lambda series, scale: len(series) > 0)
@deal.pre(lambda series, scale: is_1hz_spaced(series))
@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
def find_threshold_candidates(
    series: pl.DataFrame, scale: Scale
) -> list[tuple[int, int]]:
    """Find candidate block windows by hysteresis over raw power.

    Args:
        series: A 1 Hz-gridded time series with ``power`` and
            ``baseline_power`` columns, as returned by
            :func:`~intervals.preprocessing.resample_to_1hz` and
            :func:`~intervals.preprocessing.compute_baseline`; must not be
            empty.
        scale: The time scale's tuning parameters (unused by the threshold
            itself, kept for a uniform per-scale call signature).

    Returns:
        Candidate windows as ``(start_index, end_index)`` row-index pairs
        into ``series``, chronologically sorted and non-overlapping. A row
        with no power or baseline reading (a gap) can never be "in" a
        block and ends one already open.

    Raises:
        deal.PreContractError: If ``series`` is empty or not spaced exactly
            one second apart.

    >>> from datetime import UTC, datetime, timedelta
    >>> import polars as pl
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(20)],
    ...         "power": [100.0] * 5 + [250.0] * 10 + [100.0] * 5,
    ...         "baseline_power": [100.0] * 20,
    ...     }
    ... )
    >>> from intervals.config import DEFAULT_SCALE
    >>> find_threshold_candidates(series, DEFAULT_SCALE)
    [(5, 15)]
    """
    in_block = False
    flags: list[bool] = []
    for power, baseline in zip(
        series["power"].to_list(), series["baseline_power"].to_list(), strict=True
    ):
        if power is None or baseline is None:
            in_block = False
        elif in_block:
            in_block = power >= baseline * (1 + HYSTERESIS_EXIT_FRACTION) + (
                HYSTERESIS_MARGIN_W
            )
        else:
            in_block = power >= baseline * (1 + HYSTERESIS_ENTRY_FRACTION) + (
                HYSTERESIS_MARGIN_W
            )
        flags.append(in_block)
    return _true_runs(flags)
