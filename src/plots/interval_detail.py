"""Close-up of a single detected interval: power, heart rate and cadence."""

import math
from typing import Final, NamedTuple

import deal
import polars as pl
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from intervals.blocks import IntervalBlock

_MISSING_COLOR: Final = "#888888"
"""Grey for the "nothing recorded here" note, so an empty panel reads as an
absent sensor rather than as a measurement."""

_AVERAGE_COLOR: Final = "#c1440e"
_TARGET_COLOR: Final = "#333333"


class _Channel(NamedTuple):
    """One panel of the close-up.

    Attributes:
        column: Column of the block's series to draw.
        name: German name of the measurement, used both as the axis label
            and in the note shown when the channel was never recorded.
        unit: Unit shown after the name on the axis.
        color: Line colour, matching the same measurement's colour in the
            workout timeline.
    """

    column: str
    name: str
    unit: str
    color: str


_CHANNELS: Final[tuple[_Channel, ...]] = (
    _Channel("power", "Leistung", "W", "#c1440e"),
    _Channel("heart_rate", "Herzfrequenz", "bpm", "#2ca02c"),
    _Channel("cadence", "Trittfrequenz", "rpm", "#1f77b4"),
)
"""The three channels the close-up shows, in the order they are stacked.
Power first because the question the view answers — how steady was this
effort — is a question about power; heart rate and cadence explain it."""


def _draw_channel(
    axes: Axes, channel: _Channel, minutes: list[float], values: list[float | None]
) -> None:
    """Draw one channel's panel, or a note if the sensor recorded nothing.

    An unrecorded channel keeps its panel instead of being dropped: a
    missing measurement is information, and silently shrinking the figure
    to two panels would hide that the athlete rode without the sensor.
    """
    axes.set_ylabel(f"{channel.name} ({channel.unit})")
    if all(value is None for value in values):
        axes.text(
            0.5,
            0.5,
            f"Keine {channel.name} aufgezeichnet",
            transform=axes.transAxes,
            horizontalalignment="center",
            verticalalignment="center",
            color=_MISSING_COLOR,
        )
        axes.set_yticks([])
        return
    # None would break matplotlib; NaN is what it draws as a gap in the line.
    axes.plot(
        minutes,
        [math.nan if value is None else value for value in values],
        color=channel.color,
        linewidth=1,
    )


@deal.pre(lambda block_series, block, target_power_w=None: len(block_series) > 0)
@deal.pre(
    lambda block_series, block, target_power_w=None: (
        target_power_w is None or target_power_w > 0
    )
)
def plot_interval_detail(
    block_series: pl.DataFrame,
    block: IntervalBlock,
    target_power_w: int | None = None,
) -> Figure:
    """Draw one interval's power, heart rate and cadence over its own time.

    The overview chart shows where the intervals were; this one shows what
    happened inside a single one. Power is drawn raw rather than smoothed,
    because the question here is precisely how much the effort wobbled —
    smoothing would answer it in the athlete's favour. The block's average
    is drawn across it as the line the ride should have hugged.

    The x-axis starts at zero for every block, so two repetitions can be
    compared by opening them one after the other without re-reading the
    scale.

    Args:
        block_series: One block's rows as returned by
            :func:`~intervals.detail.slice_block`, with ``timestamp``,
            ``power``, ``heart_rate`` and ``cadence`` columns; must not be
            empty.
        block: The block those rows belong to, for its average power.
        target_power_w: The planned power for the session, drawn as a
            second reference line, or None if the athlete gave no plan;
            must be positive if given.

    Returns:
        A matplotlib figure with three stacked panels sharing a time axis.

    Raises:
        deal.PreContractError: If ``block_series`` is empty or
            ``target_power_w`` is not positive.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> block_series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(3)],
    ...         "power": [200, 210, 220],
    ...         "heart_rate": [150, 152, 155],
    ...         "cadence": [90, 91, 92],
    ...     }
    ... )
    >>> block = IntervalBlock(
    ...     start=start,
    ...     end=start + timedelta(seconds=3),
    ...     duration=timedelta(seconds=3),
    ...     avg_power_w=210.0,
    ...     avg_power_relative_to_ftp=None,
    ...     avg_heart_rate=152.3,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=0.97,
    ... )
    >>> figure = plot_interval_detail(block_series, block)
    >>> len(figure.axes)
    3
    """
    timestamps = block_series["timestamp"].to_list()
    minutes = [(moment - timestamps[0]).total_seconds() / 60 for moment in timestamps]

    figure = Figure(figsize=(8, 7))
    panels = figure.subplots(len(_CHANNELS), 1, sharex=True)

    for axes, channel in zip(panels, _CHANNELS, strict=True):
        values = [
            None if value is None else float(value)
            for value in block_series[channel.column].to_list()
        ]
        _draw_channel(axes, channel, minutes, values)

    power_axes = panels[0]
    power_axes.axhline(
        block.avg_power_w,
        color=_AVERAGE_COLOR,
        linestyle="--",
        linewidth=1,
        label=f"Ø {block.avg_power_w:.0f} W",
    )
    if target_power_w is not None:
        power_axes.axhline(
            target_power_w,
            color=_TARGET_COLOR,
            linestyle=":",
            linewidth=1,
            label=f"Ziel {target_power_w} W",
        )
    power_axes.legend(loc="upper right")

    panels[-1].set_xlabel("Zeit im Intervall (min)")
    figure.tight_layout()
    return figure
