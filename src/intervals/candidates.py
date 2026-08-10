"""Single-scale candidate search: smoothing, CUSUM edge-finding, hysteresis.

Runs independently for one :class:`~intervals.config.Scale` at a time.
Later steps (merging, filtering — added in following commits) turn these
refined windows into real candidates; multiple scales and cross-scale
consolidation are a later milestone.
"""

from itertools import pairwise

import deal
import numpy as np
import polars as pl
from scipy.signal import find_peaks

from intervals.config import (
    HYSTERESIS_ENTRY_FRACTION,
    HYSTERESIS_EXIT_FRACTION,
    Scale,
)
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


def _find_crossing(
    signal: np.ndarray, around: int, threshold: float, margin: int, rising: bool
) -> int | None:
    """Find where ``signal`` crosses ``threshold``, closest to ``around``.

    ``rising=True`` looks for the signal moving from below to at-or-above
    the threshold (a block's entry); ``rising=False`` looks for the reverse
    (a block's exit). Search is limited to ``around ± margin`` — the rough
    CUSUM edge is already close, so the true crossing shouldn't be far. A
    ``NaN`` value (a recording gap) never satisfies either comparison, so
    it's silently skipped rather than needing special-casing.

    Args:
        signal: The signal to search for a crossing.
        around: Row index to search near.
        threshold: The level to find a crossing of.
        margin: How many samples to search on either side of ``around``.
        rising: Direction of the crossing to look for.

    Returns:
        The crossing index closest to ``around``, or None if the signal
        never crosses ``threshold`` in that direction within the window.
    """
    search_start = max(1, around - margin)
    search_end = min(len(signal) - 1, around + margin)
    crossings = [
        i
        for i in range(search_start, search_end + 1)
        if (
            signal[i - 1] < threshold <= signal[i]
            if rising
            else signal[i - 1] >= threshold > signal[i]
        )
    ]
    return min(crossings, key=lambda i: abs(i - around)) if crossings else None


def _refine_candidate(
    power: np.ndarray, rough: tuple[int, int], scale: Scale
) -> tuple[int, int] | None:
    """Refine one rough candidate's edges by hysteresis around its target.

    Deliberately searches the *raw* power, not the smoothed signal the
    rough window came from: smoothing is what makes CUSUM robust to noise,
    but a centred moving average also blurs a real, sharp edge over its
    whole window width — exactly the imprecision this step exists to
    correct. The target level (median power within the rough window) is
    similarly robust to noise without needing to be smoothed first.

    Using a lower exit fraction than entry fraction (hysteresis, not a
    single shared threshold) means a short dip inside the block doesn't
    immediately end it — the most common way a single threshold fails on
    outdoor rides.

    Args:
        power: The raw power signal the rough window was found on.
        rough: The candidate's rough ``(start_index, end_index)``.
        scale: The time scale's tuning parameters.

    Returns:
        The refined ``(start_index, end_index)``, or None if the signal
        never reaches the entry fraction of the target near the rough
        start — the candidate never really "entered" a block.
    """
    start, end = rough
    target = float(np.nanmedian(power[start : end + 1]))
    margin = scale.smoothing_window_s

    refined_start = _find_crossing(
        power, start, HYSTERESIS_ENTRY_FRACTION * target, margin, rising=True
    )
    if refined_start is None:
        return None

    refined_end = _find_crossing(
        power, end, HYSTERESIS_EXIT_FRACTION * target, margin, rising=False
    )
    if refined_end is None or refined_end <= refined_start:
        refined_end = end

    return refined_start, refined_end


@deal.ensure(lambda _: all(start < end for start, end in _.result))
def refine_candidates(
    power: np.ndarray, rough_candidates: list[tuple[int, int]], scale: Scale
) -> list[tuple[int, int]]:
    """Refine each rough candidate's edges by hysteresis, dropping failures.

    Args:
        power: The raw power signal the rough windows were found on (as
            ``NaN``-for-missing floats, not the smoothed CUSUM input).
        rough_candidates: Rough ``(start_index, end_index)`` windows, as
            returned by :func:`find_rough_candidates`.
        scale: The time scale's tuning parameters.

    Returns:
        The refined windows, in the same order, minus any candidate whose
        signal never reached the entry fraction of its own target level.

    >>> import numpy as np
    >>> power = np.array([100.0] * 3 + [250.0] * 6 + [100.0] * 3)
    >>> from intervals.config import MEDIUM_SCALE
    >>> refine_candidates(power, [(2, 9)], MEDIUM_SCALE)
    [(3, 9)]
    """
    refined = [_refine_candidate(power, rough, scale) for rough in rough_candidates]
    return [candidate for candidate in refined if candidate is not None]
