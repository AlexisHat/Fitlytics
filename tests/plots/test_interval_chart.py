"""Tests for plots.interval_chart."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

import deal
import polars as pl
import pytest
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from intervals.blocks import IntervalBlock
from plots.interval_chart import plot_power_with_intervals

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(powers: Sequence[int | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + timedelta(seconds=i) for i in range(len(powers))],
            "power": powers,
            "smoothed_power": [None if p is None else float(p) for p in powers],
        }
    )


def _block(start_s: int, end_s: int, avg_power_w: float = 250.0) -> IntervalBlock:
    start = START + timedelta(seconds=start_s)
    end = START + timedelta(seconds=end_s)
    return IntervalBlock(
        start=start,
        end=end,
        duration=end - start,
        avg_power_w=avg_power_w,
        avg_power_relative_to_ftp=None,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=1.0,
    )


def _shaded_spans(fig: Figure) -> list[tuple[float, float]]:
    """Left and right edge, in minutes, of every shaded background region."""
    spans: list[tuple[float, float]] = []
    for patch in fig.axes[0].patches:
        # axvspan yields a Rectangle whose x is in data coordinates (minutes)
        # while its y spans the axes; only the x edges are meaningful here.
        rectangle = cast(Rectangle, patch)
        left = float(rectangle.get_x())
        spans.append((left, left + float(rectangle.get_width())))
    return spans


def _line_y(fig: Figure, index: int) -> list[float]:
    """The y values of one plotted line, as plain floats.

    ``get_ydata`` hands back the original list for a plotted curve but a
    numpy array for a line matplotlib built itself (``axhline``), so both
    are normalised here.
    """
    values = cast(Sequence[float], fig.axes[0].lines[index].get_ydata())
    return [float(value) for value in values]


def test_plot_shades_one_region_per_detected_block() -> None:
    fig = plot_power_with_intervals(
        _series([100] * 600), [_block(60, 180), _block(300, 420)]
    )

    assert len(_shaded_spans(fig)) == 2


def test_plot_shades_the_block_at_its_real_position_in_minutes() -> None:
    """The whole point of the chart: a block must sit where it happened, so
    the athlete can check it against the curve underneath."""
    fig = plot_power_with_intervals(_series([100] * 600), [_block(120, 300)])

    assert _shaded_spans(fig) == [(2.0, 5.0)]


def test_plot_without_any_block_draws_the_bare_curve() -> None:
    fig = plot_power_with_intervals(_series([100] * 60), [])

    assert _shaded_spans(fig) == []
    assert len(fig.axes[0].lines) == 2


def test_plot_draws_raw_and_smoothed_power_as_separate_lines() -> None:
    fig = plot_power_with_intervals(_series([100] * 60), [])

    assert len(fig.axes[0].lines) == 2


def test_plot_breaks_the_curve_at_a_recording_gap() -> None:
    """A gap must read as missing data, not as a straight line drawn across
    it — matplotlib draws NaN as a break, None would raise."""
    powers: list[int | None] = [100] * 20 + [None] * 20 + [100] * 20

    fig = plot_power_with_intervals(_series(powers), [])

    assert any(math.isnan(value) for value in _line_y(fig, 1))


def test_plot_draws_a_target_line_when_a_plan_exists() -> None:
    fig = plot_power_with_intervals(_series([100] * 60), [], target_power_w=250)

    horizontal = [
        index
        for index in range(len(fig.axes[0].lines))
        if _line_y(fig, index) == [250.0, 250.0]
    ]
    assert len(horizontal) == 1


def test_plot_draws_no_target_line_without_a_plan() -> None:
    fig = plot_power_with_intervals(_series([100] * 60), [])

    assert fig.axes[0].get_legend() is None


def test_plot_scales_the_axis_to_the_smoothed_curve_not_raw_spikes() -> None:
    """A ride whose raw power spikes to 600 W but never sustains above 150 W
    must still use the full height for the part that matters."""
    powers: list[int | None] = [150] * 60
    series = _series(powers).with_columns(pl.Series("power", [600] + [150] * 59))

    _, top = plot_power_with_intervals(series, []).axes[0].get_ylim()

    assert top < 300


def test_plot_keeps_the_target_line_inside_the_axis() -> None:
    fig = plot_power_with_intervals(_series([100] * 60), [], target_power_w=400)

    _, top = fig.axes[0].get_ylim()

    assert top > 400


def test_plot_title_names_the_number_of_blocks() -> None:
    fig = plot_power_with_intervals(_series([100] * 600), [_block(60, 180)])

    assert "1" in fig.axes[0].get_title()


def test_plot_rejects_an_empty_series() -> None:
    empty = _series([100]).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        plot_power_with_intervals(empty, [])


@pytest.mark.parametrize("target", [0, -1])
def test_plot_rejects_a_non_positive_target_power(target: int) -> None:
    with pytest.raises(deal.PreContractError):
        plot_power_with_intervals(_series([100] * 60), [], target_power_w=target)
