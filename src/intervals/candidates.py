"""Single-scale candidate search: smoothing, CUSUM-based edge-finding.

Runs independently for one :class:`~intervals.config.Scale` at a time.
Later steps (hysteresis refinement, merging, filtering — added in
following commits) turn these rough windows into real candidates; multiple
scales and cross-scale consolidation are a later milestone.
"""

from itertools import pairwise

import deal
import numpy as np
import polars as pl
from scipy.signal import find_peaks

from intervals.config import Scale
from intervals.preprocessing import is_1hz_spaced


def _smooth_power(series: pl.DataFrame, scale: Scale) -> pl.Series:
    """Centred moving-average smoothing of power for one time scale.

    A trailing average would shift every edge later than it really is;
    centring keeps the smoothed signal's edges aligned with the raw one.
    """
    return (
        series["power"]
        .cast(pl.Float64)
        .rolling_mean(window_size=scale.smoothing_window_s, center=True, min_samples=1)
    )


def _cusum(smoothed_power: pl.Series, baseline_power: pl.Series) -> np.ndarray:
    """Cumulative sum of the smoothed signal's deviation from baseline.

    The sum rises while power is above baseline and falls while it's
    below, so a block shows up as a rise in this signal. A missing value on
    either side (a recording gap, or too little data for a baseline) is
    treated as "at baseline" here, so the sum keeps flowing across it
    instead of turning null for the rest of the ride — a candidate that
    actually spans the gap is rejected later by a dedicated filter, not by
    poisoning this running total.
    """
    deviation = (smoothed_power - baseline_power).fill_null(0.0)
    return deviation.cum_sum().to_numpy()


@deal.pre(lambda cusum, scale: scale.prominence_ws > 0)
@deal.ensure(lambda _: all(start < end for start, end in _.result))
@deal.ensure(lambda _: all(a[1] <= b[0] for a, b in pairwise(_.result)))
def _pair_edges(cusum: np.ndarray, scale: Scale) -> list[tuple[int, int]]:
    """Pair CUSUM local minima with the next local maximum into windows.

    A local minimum is where the signal turns from falling to rising —
    the point a block most likely starts. The next local maximum is where
    it turns from rising to falling again — the point that block most
    likely ends. Peaks are found by prominence rather than absolute height,
    so the threshold reflects how much a rise stands out from its
    surroundings ("work over baseline") rather than an arbitrary level.

    Args:
        cusum: The cumulative deviation-from-baseline signal.
        scale: The time scale's tuning parameters; ``prominence_ws`` must
            be positive.

    Returns:
        Rough candidate windows as ``(start_index, end_index)`` row-index
        pairs into the series ``cusum`` was built from, chronologically
        sorted and non-overlapping. A block still rising at the very last
        sample (no cool-down before the recording ends) is closed at that
        last sample rather than dropped — ``find_peaks`` never reports a
        boundary point as a peak, so without this the block would
        otherwise vanish entirely.

    Raises:
        deal.PreContractError: If ``scale.prominence_ws`` is not positive.

    >>> import numpy as np
    >>> # falls to a dip (block start), rises sharply (a block), falls back
    >>> cusum = np.array([0, -3, -8, -3, 6, 16, 26, 16, 6, -3, -8], dtype=float)
    >>> from intervals.config import MEDIUM_SCALE
    >>> scale = MEDIUM_SCALE._replace(prominence_ws=5.0)
    >>> _pair_edges(cusum, scale)
    [(2, 6)]
    """
    minima, _ = find_peaks(-cusum, prominence=scale.prominence_ws)
    maxima, _ = find_peaks(cusum, prominence=scale.prominence_ws)

    events = sorted(
        [(int(index), "min") for index in minima]
        + [(int(index), "max") for index in maxima]
    )
    candidates: list[tuple[int, int]] = []
    open_start: int | None = None
    for index, kind in events:
        if kind == "min":
            if open_start is None:
                open_start = index
        elif open_start is not None:
            candidates.append((open_start, index))
            open_start = None

    last_index = len(cusum) - 1
    if open_start is not None and open_start < last_index:
        # The recording ends while still rising, e.g. no cool-down after the
        # last block: find_peaks never sees a maximum because it never
        # considers the series' own boundary a peak. Close the candidate at
        # the last sample instead of silently dropping it.
        candidates.append((open_start, last_index))

    return candidates


@deal.pre(lambda series, scale: len(series) > 0)
@deal.pre(lambda series, scale: is_1hz_spaced(series))
def find_rough_candidates(series: pl.DataFrame, scale: Scale) -> list[tuple[int, int]]:
    """Find rough candidate block windows for one time scale.

    Args:
        series: A 1 Hz-gridded time series with ``power`` and
            ``baseline_power`` columns, as returned by
            :func:`~intervals.preprocessing.resample_to_1hz` and
            :func:`~intervals.preprocessing.compute_baseline`; must not be
            empty.
        scale: The time scale's tuning parameters.

    Returns:
        Rough candidate windows as ``(start_index, end_index)`` row-index
        pairs into ``series``, not yet refined, merged or filtered.

    Raises:
        deal.PreContractError: If ``series`` is empty or not spaced exactly
            one second apart.
    """
    smoothed = _smooth_power(series, scale)
    cusum = _cusum(smoothed, series["baseline_power"])
    return _pair_edges(cusum, scale)
