"""Smoothing a day-by-day series into a readable multi-day trend."""

from collections.abc import Sequence

import deal
import polars as pl


def _within_input_range(
    smoothed: Sequence[float | None], daily_values: Sequence[float | None]
) -> bool:
    """Whether every smoothed value lies within the range of the inputs.

    >>> _within_input_range([2.0], [1.0, 3.0])
    True
    >>> _within_input_range([4.0], [1.0, 3.0])
    False
    """
    present = [value for value in daily_values if value is not None]
    if not present:
        return True
    lowest, highest = min(present), max(present)
    return all(value is None or lowest <= value <= highest for value in smoothed)


@deal.pre(lambda daily_values, window_days: window_days > 0)
@deal.ensure(lambda _: len(_.result) == len(_.daily_values))
@deal.ensure(lambda _: _within_input_range(_.result, _.daily_values))
def rolling_average(
    daily_values: Sequence[float | None], window_days: int
) -> list[float | None]:
    """Average each day with its neighbours to expose the underlying trend.

    Night-to-night recovery figures swing far more than the trend they
    carry — a single poor night drops HRV well below a fortnight's range
    without meaning anything about form. Averaging over a window makes the
    slower movement legible while keeping the daily values available to
    plot alongside it.

    Args:
        daily_values: One value per day in chronological order, None where the
            day has no measurement. Missing days are skipped rather than
            counted as zero, which would drag the average toward it.
        window_days: Width of the centred window in days; must be
            positive. The window shrinks at both ends of the series rather
            than padding it with invented values.

    Returns:
        One averaged value per input day, in the same order. A day whose
        whole window is missing stays None.

    Raises:
        deal.PreContractError: If ``window_days`` is not positive.

    >>> rolling_average([1.0, 2.0, 3.0], 3)
    [1.5, 2.0, 2.5]
    >>> rolling_average([1.0, None, 3.0], 3)
    [1.0, 2.0, 3.0]
    >>> rolling_average([10.0, 20.0], 1)
    [10.0, 20.0]
    """
    smoothed = pl.Series(daily_values, dtype=pl.Float64).rolling_mean(
        window_days, min_samples=1, center=True
    )
    present = [value for value in daily_values if value is not None]
    if not present:
        return list(smoothed.to_list())

    # polars slides the window over a running sum, adding each value as it
    # enters and subtracting it as it leaves. A large value leaving the
    # window does not cancel exactly, so the mean of two zeros after a
    # 999 W day comes out as -5.7e-14 rather than 0. Clamping restores the
    # guarantee an average has mathematically but this algorithm loses —
    # without it a physiological measurement could come out negative.
    lowest, highest = min(present), max(present)
    return [
        None if value is None else min(max(value, lowest), highest)
        for value in smoothed.to_list()
    ]
