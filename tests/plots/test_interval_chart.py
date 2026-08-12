"""Tests for plots.interval_chart."""

from datetime import UTC, datetime, timedelta
from typing import cast

from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from intervals.blocks import IntervalBlock
from plots.interval_chart import plot_interval_blocks

START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(fig: Figure) -> list[Rectangle]:
    return cast(BarContainer, fig.axes[0].containers[0]).patches


def _block(avg_power_w: float, duration_minutes: float) -> IntervalBlock:
    duration = timedelta(minutes=duration_minutes)
    return IntervalBlock(
        start=START,
        end=START + duration,
        duration=duration,
        avg_power_w=avg_power_w,
        avg_power_relative_to_ftp=None,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=1.0,
    )


def test_plot_interval_blocks_bar_height_is_average_power() -> None:
    fig = plot_interval_blocks([_block(260.0, 4), _block(240.0, 2)])

    heights = [bar.get_height() for bar in _bars(fig)]

    assert heights == [260.0, 240.0]


def test_plot_interval_blocks_bar_width_is_duration_in_minutes() -> None:
    fig = plot_interval_blocks([_block(200.0, 4), _block(200.0, 1.5)])

    widths = [bar.get_width() for bar in _bars(fig)]

    assert widths == [4.0, 1.5]


def test_plot_interval_blocks_places_bars_back_to_back() -> None:
    """The second bar's left edge sits exactly where the first bar ends,
    i.e. the bars are placed by cumulative duration, not evenly spaced."""
    fig = plot_interval_blocks([_block(200.0, 4), _block(200.0, 2), _block(200.0, 1)])

    left_edges = [bar.get_x() for bar in _bars(fig)]

    assert left_edges == [0.0, 4.0, 6.0]


def test_plot_interval_blocks_single_block_starts_at_zero() -> None:
    fig = plot_interval_blocks([_block(220.0, 3)])

    bars = _bars(fig)

    assert len(bars) == 1
    assert bars[0].get_x() == 0.0
