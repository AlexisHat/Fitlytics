"""Bar chart comparing a workout's detected interval blocks."""

from typing import Final

from matplotlib.figure import Figure

from intervals.blocks import IntervalBlock

_BAR_COLOR: Final = "#c1440e"
"""Same orange as the power panel in the interactive timeline and the power
zone bar chart."""


def plot_interval_blocks(blocks: list[IntervalBlock]) -> Figure:
    """Draw a bar chart comparing a workout's detected interval blocks.

    Each block gets one bar: height is its average power, width is its
    duration — so a rep that faded (lower bar) or ran short (narrower bar)
    is visible at a glance, without reading the numbers themselves. Bars
    are placed back to back in detection order rather than at their real
    clock position, since comparing the blocks against each other is the
    point, not reconstructing the ride's timeline.

    Args:
        blocks: The workout's detected interval blocks, in chronological
            order; must not be empty.

    Returns:
        A matplotlib figure with one bar per block.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> block_a = IntervalBlock(
    ...     start=start,
    ...     end=start + timedelta(minutes=4),
    ...     duration=timedelta(minutes=4),
    ...     avg_power_w=260.0,
    ...     avg_power_relative_to_ftp=None,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=1.0,
    ... )
    >>> block_b = block_a.model_copy(
    ...     update={"avg_power_w": 240.0, "duration": timedelta(minutes=2)}
    ... )
    >>> fig = plot_interval_blocks([block_a, block_b])
    >>> [round(float(bar.get_height()), 1) for bar in fig.axes[0].patches]
    [260.0, 240.0]
    >>> [round(float(bar.get_width()), 1) for bar in fig.axes[0].patches]
    [4.0, 2.0]
    """
    widths = [block.duration.total_seconds() / 60 for block in blocks]
    heights = [block.avg_power_w for block in blocks]

    left_edges = [0.0]
    for width in widths[:-1]:
        left_edges.append(left_edges[-1] + width)

    fig = Figure()
    ax = fig.add_subplot()
    ax.bar(
        left_edges,
        heights,
        width=widths,
        align="edge",
        color=_BAR_COLOR,
        edgecolor="white",
        linewidth=1,
    )
    ax.set_xlabel("Kumulierte Dauer (min)")
    ax.set_ylabel("Ø Leistung (W)")
    ax.set_title("Intervall-Vergleich")
    fig.tight_layout()
    return fig
