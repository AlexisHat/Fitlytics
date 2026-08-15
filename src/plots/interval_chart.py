"""Power over the ride's timeline, with the detected interval blocks shaded."""

import math
from datetime import datetime
from typing import Final

import deal
import polars as pl
from matplotlib.figure import Figure

from intervals.blocks import IntervalBlock

_POWER_COLOR: Final = "#c1440e"
"""Same orange as the power panel in the interactive timeline and the power
zone bar chart."""

_RAW_POWER_COLOR: Final = "#cccccc"
"""Grey for the unsmoothed signal behind the curve — present so the reader
can see the real spread of the data, quiet enough not to compete with it."""

_RAW_ALPHA: Final = 0.5
"""Spikes clipped by the y-axis would otherwise read as solid full-height
bars rather than as the brief outliers they are."""

_BLOCK_ALPHA: Final = 0.18
"""How strongly a detected block tints the background. Low enough that the
power curve stays fully readable through it, since checking the curve
against the shading is the entire point of this chart."""

_TARGET_COLOR: Final = "#333333"


def _elapsed_minutes(timestamps: list[datetime], moment: datetime) -> float:
    """Minutes from the first timestamp to ``moment``.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> _elapsed_minutes([start], start + timedelta(minutes=3))
    3.0
    """
    return (moment - timestamps[0]).total_seconds() / 60


_HEADROOM: Final = 1.15
"""How much room to leave above the highest smoothed value, so the curve
does not run into the top edge of the axes."""

_EMPTY_SCALE_TOP: Final = 1.0
"""Y-axis top for a ride with no power data at all, where any positive
number does — matplotlib rejects a zero-height axis."""


def _top_of_scale(smoothed: list[float], target_power_w: int | None) -> float:
    """Choose the y-axis top from the smoothed curve, not the raw readings.

    Single wild seconds reach several times the power actually sustained,
    and letting them set the scale squeezes the whole interesting range
    into the bottom of the chart. They stay drawn, just clipped.

    >>> round(_top_of_scale([100.0, 200.0], None), 1)
    230.0
    >>> round(_top_of_scale([100.0], 300), 1)
    345.0
    """
    candidates = [value for value in smoothed if not math.isnan(value)]
    if target_power_w is not None:
        candidates.append(float(target_power_w))
    if not candidates:
        return _EMPTY_SCALE_TOP
    return max(candidates) * _HEADROOM


@deal.pre(lambda series, blocks, target_power_w=None: len(series) > 0)
@deal.pre(
    lambda series, blocks, target_power_w=None: (
        target_power_w is None or target_power_w > 0
    )
)
def plot_power_with_intervals(
    series: pl.DataFrame,
    blocks: list[IntervalBlock],
    target_power_w: int | None = None,
) -> Figure:
    """Draw the ride's power curve with every detected interval shaded.

    The chart exists to make detection checkable: an athlete who can see
    the blocks lying on top of their own power curve can tell at a glance
    whether the right stretches were found, which no amount of summary
    statistics conveys. The smoothed signal is drawn as the main curve
    because that is what detection actually ran on, so the shaded edges
    line up with what the algorithm saw rather than with a noisier signal
    it never used; the raw readings stay visible behind it in grey.

    Recording gaps break the curve instead of being bridged by a straight
    line, matching how detection treats them as hard block boundaries.

    Args:
        series: The 1 Hz-gridded time series detection ran on, with
            ``timestamp``, ``power`` and ``smoothed_power`` columns; must
            not be empty.
        blocks: The detected interval blocks, in chronological order. May
            be empty, which simply yields the bare power curve.
        target_power_w: The planned power for this session, drawn as a
            reference line, or None if the athlete gave no plan; must be
            positive if given.

    Returns:
        A matplotlib figure with elapsed time in minutes on the x-axis and
        power in watts on the y-axis.

    Raises:
        deal.PreContractError: If ``series`` is empty or ``target_power_w``
            is not positive.

    >>> import polars as pl
    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(10)],
    ...         "power": [100] * 10,
    ...         "smoothed_power": [100.0] * 10,
    ...     }
    ... )
    >>> block = IntervalBlock(
    ...     start=start + timedelta(seconds=2),
    ...     end=start + timedelta(seconds=6),
    ...     duration=timedelta(seconds=4),
    ...     avg_power_w=250.0,
    ...     avg_power_relative_to_ftp=None,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=1.0,
    ... )
    >>> fig = plot_power_with_intervals(series, [block])
    >>> len(fig.axes[0].patches)
    1
    """
    timestamps = series["timestamp"].to_list()
    minutes = [_elapsed_minutes(timestamps, moment) for moment in timestamps]
    # None would break matplotlib; NaN is what it draws as a gap in the line.
    raw = [math.nan if p is None else float(p) for p in series["power"].to_list()]
    smoothed = [
        math.nan if p is None else p for p in series["smoothed_power"].to_list()
    ]

    fig = Figure()
    ax = fig.add_subplot()
    ax.plot(minutes, raw, color=_RAW_POWER_COLOR, linewidth=0.5, alpha=_RAW_ALPHA)
    ax.plot(minutes, smoothed, color=_POWER_COLOR, linewidth=1.2)

    for block in blocks:
        ax.axvspan(
            _elapsed_minutes(timestamps, block.start),
            _elapsed_minutes(timestamps, block.end),
            color=_POWER_COLOR,
            alpha=_BLOCK_ALPHA,
            linewidth=0,
        )

    if target_power_w is not None:
        ax.axhline(
            target_power_w,
            color=_TARGET_COLOR,
            linestyle="--",
            linewidth=1,
            label=f"Ziel {target_power_w} W",
        )
        ax.legend(loc="upper right")

    ax.set_xlabel("Zeit (min)")
    ax.set_ylabel("Leistung (W)")
    ax.set_title(f"Leistungsverlauf mit {len(blocks)} erkannten Intervallen")
    ax.set_xlim(0, minutes[-1] if minutes[-1] > 0 else 1)
    ax.set_ylim(0, _top_of_scale(smoothed, target_power_w))
    fig.tight_layout()
    return fig
