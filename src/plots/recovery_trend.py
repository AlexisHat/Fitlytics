"""Multi-day trend of the Whoop recovery figures, against training days."""

from datetime import date
from typing import Final

import deal
from matplotlib.figure import Figure

from analysis.calendar import training_load_intensity_pct
from analysis.trends import rolling_average
from models import RecoveryDay
from plots.intensity import intensity_color

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

_WORKOUT_LINE_ALPHA: Final = 0.6
"""Workout markers must be readable at a glance without pulling attention
from the curves they are meant to explain."""

_WORKOUT_LINE_WIDTH: Final = 2.5
"""Fixed in points rather than scaled to the day, so a marker stays visible
whether the chart shows 30 days or a full year."""


def workout_marker_colors(loads: dict[date, float]) -> list[tuple[date, str]]:
    """Pair each training day with the colour its load earns on the chart.

    Args:
        loads: Training load per day, as built by
            :func:`analysis.calendar.daily_training_load`.

    Returns:
        One ``(day, colour)`` pair per training day, in date order, the
        colour being a ``#rrggbb`` string on the calendar's intensity scale.

    >>> from datetime import date
    >>> easy, hard = date(2026, 7, 16), date(2026, 7, 18)
    >>> workout_marker_colors({hard: 250.0, easy: 25.0})
    [(datetime.date(2026, 7, 16), '#8eedb0'), (datetime.date(2026, 7, 18), '#dc2626')]
    """
    return [
        (day, intensity_color(training_load_intensity_pct(load)))
        for day, load in sorted(loads.items())
    ]


@deal.pre(lambda _: len(_.days) > 0)
def plot_recovery_trend(
    days: list[RecoveryDay], workout_loads: dict[date, float] | None = None
) -> Figure:
    """Draw HRV and resting heart rate over time, daily and smoothed.

    Two stacked panels rather than one with two y-axes: the measures share
    a time axis but nothing else, and a twin axis invites reading a
    crossing point as meaningful when the two scales were chosen
    independently.

    Training days are drawn behind both curves as vertical lines in the
    calendar's own green-to-red intensity colours, so the recovery dip
    after a hard day can be read off directly instead of by comparing two
    charts side by side.

    Args:
        days: The athlete's recovery days in chronological order; must not
            be empty. Days without a measurement leave a gap in the daily
            series rather than being dropped, so the time axis stays true.
        workout_loads: Training load per day, as built by
            :func:`analysis.calendar.daily_training_load`. Days outside the
            span of ``days`` are ignored, so the caller can pass the whole
            history without trimming it. None draws no markers at all.

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
    in_span = {
        day: load
        for day, load in (workout_loads or {}).items()
        if dates[0] <= day <= dates[-1]
    }
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
        # Drawn after the curves so the axis already reads x as dates, and
        # behind them via zorder. axes comes from Figure.subplots(), which
        # matplotlib leaves untyped — same as every other call in this loop.
        for day, marker_color in workout_marker_colors(in_span):
            axes.axvline(
                day,
                color=marker_color,
                linewidth=_WORKOUT_LINE_WIDTH,
                alpha=_WORKOUT_LINE_ALPHA,
                zorder=0,
            )
        axes.set_ylabel(label)
        axes.legend(loc="upper left")

    hr_axes.set_xlabel("Datum")
    title = "Herzfrequenzvariabilität und Ruhepuls im Verlauf"
    hrv_axes.set_title(
        f"{title}, mit Trainingstagen nach Belastung" if in_span else title
    )
    figure.autofmt_xdate()
    figure.tight_layout()
    return figure
