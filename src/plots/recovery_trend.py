"""Multi-day trend of the Whoop recovery figures."""

from typing import Final

import deal
from matplotlib.figure import Figure

from analysis.trends import rolling_average
from models import RecoveryDay

_HRV_COLOR: Final = "#2ca02c"
"""Same green as the heart-rate panel elsewhere — HRV is a heart measure."""

_RESTING_HR_COLOR: Final = "#c1440e"

_DAILY_ALPHA: Final = 0.35
"""Daily values stay visible behind the trend line but must not compete
with it; the point of the chart is the slower movement."""

TREND_WINDOW_DAYS: Final = 7
"""Width of the smoothing window. A week covers the weekly rhythm of
training and sleep, so the trend line is not just a lagged copy of the
last hard day."""


@deal.pre(lambda days: len(days) > 0)
def plot_recovery_trend(days: list[RecoveryDay]) -> Figure:
    """Draw HRV and resting heart rate over time, daily and smoothed.

    Two stacked panels rather than one with two y-axes: the measures share
    a time axis but nothing else, and a twin axis invites reading a
    crossing point as meaningful when the two scales were chosen
    independently.

    Args:
        days: The athlete's recovery days in chronological order; must not
            be empty. Days without a measurement leave a gap in the daily
            series rather than being dropped, so the time axis stays true.

    Returns:
        A matplotlib figure with one panel for HRV and one for resting
        heart rate, sharing the date axis.

    Raises:
        deal.PreContractError: If ``days`` is empty.

    >>> from datetime import UTC, date, datetime
    >>> days = [
    ...     RecoveryDay(
    ...         date=date(2026, 7, day),
    ...         cycle_start=datetime(2026, 7, day, 1, 0, tzinfo=UTC),
    ...         hrv_ms=90.0 + day,
    ...         resting_hr=55,
    ...     )
    ...     for day in range(1, 4)
    ... ]
    >>> figure = plot_recovery_trend(days)
    >>> len(figure.axes)
    2
    """
    dates = [day.date for day in days]
    hrv = [day.hrv_ms for day in days]
    resting_hr = [
        float(day.resting_hr) if day.resting_hr is not None else None for day in days
    ]

    figure = Figure(figsize=(10, 6))
    hrv_axes, hr_axes = figure.subplots(2, 1, sharex=True)

    for axes, values, colour, label in (
        (hrv_axes, hrv, _HRV_COLOR, "HRV (ms)"),
        (hr_axes, resting_hr, _RESTING_HR_COLOR, "Ruhepuls (bpm)"),
    ):
        axes.plot(dates, values, color=colour, linewidth=0.8, alpha=_DAILY_ALPHA)
        axes.plot(
            dates,
            rolling_average(values, TREND_WINDOW_DAYS),
            color=colour,
            linewidth=2,
            label=f"{TREND_WINDOW_DAYS}-Tage-Mittel",
        )
        axes.set_ylabel(label)
        axes.legend(loc="upper left")

    hr_axes.set_xlabel("Datum")
    hrv_axes.set_title("Herzfrequenzvariabilität und Ruhepuls im Verlauf")
    figure.autofmt_xdate()
    figure.tight_layout()
    return figure
