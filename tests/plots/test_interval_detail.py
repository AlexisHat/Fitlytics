"""Tests for plots.interval_detail."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

import deal
import polars as pl
import pytest
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from intervals.blocks import IntervalBlock
from plots.interval_detail import plot_interval_detail

START = datetime(2026, 1, 1, tzinfo=UTC)


def _block_series(
    powers: Sequence[int | None],
    heart_rates: Sequence[int | None] | None = None,
    cadences: Sequence[int | None] | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + timedelta(seconds=i) for i in range(len(powers))],
            "power": list(powers),
            "heart_rate": (
                list(heart_rates) if heart_rates is not None else [None] * len(powers)
            ),
            "cadence": (
                list(cadences) if cadences is not None else [None] * len(powers)
            ),
        }
    )


def _block(avg_power_w: float = 210.0) -> IntervalBlock:
    return IntervalBlock(
        start=START,
        end=START + timedelta(minutes=4),
        duration=timedelta(minutes=4),
        avg_power_w=avg_power_w,
        avg_power_relative_to_ftp=None,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=0.95,
    )


def _y_values(line: Line2D) -> list[float]:
    """The line's y data as plain floats.

    ``get_ydata`` hands back the original list for a plotted curve but a
    numpy array for a matplotlib-drawn one such as ``axhline``.
    """
    return [float(value) for value in cast(Sequence[float], line.get_ydata())]


def _x_values(line: Line2D) -> list[float]:
    """The line's x data as plain floats, for the same reason."""
    return [float(value) for value in cast(Sequence[float], line.get_xdata())]


def _note_texts(axes: Axes) -> list[str]:
    return [text.get_text() for text in axes.texts]


def test_one_panel_per_channel() -> None:
    figure = plot_interval_detail(_block_series([200, 210, 220]), _block())

    assert len(figure.axes) == 3


def test_power_is_drawn_raw_rather_than_smoothed() -> None:
    """The view exists to show how much the effort wobbled, so the spikes
    must survive into the chart."""
    powers = [200, 260, 180]

    figure = plot_interval_detail(_block_series(powers), _block())

    assert _y_values(figure.axes[0].lines[0]) == [200.0, 260.0, 180.0]


def test_the_blocks_average_is_drawn_across_the_power_panel() -> None:
    figure = plot_interval_detail(_block_series([200, 220]), _block(avg_power_w=210.0))

    average_line = figure.axes[0].lines[-1]
    assert set(_y_values(average_line)) == {210.0}


def test_the_target_line_is_drawn_when_a_plan_was_entered() -> None:
    figure = plot_interval_detail(
        _block_series([200, 220]), _block(), target_power_w=250
    )

    drawn = {value for line in figure.axes[0].lines for value in _y_values(line)}
    assert 250.0 in drawn


def test_no_target_line_without_a_plan() -> None:
    figure = plot_interval_detail(_block_series([200, 220]), _block())

    legend = figure.axes[0].get_legend()
    assert legend is not None
    labels = [text.get_text() for text in legend.get_texts()]
    assert not any("Ziel" in label for label in labels)


def test_a_recording_gap_breaks_the_line_instead_of_reading_as_zero() -> None:
    powers: list[int | None] = [200, None, 220]

    figure = plot_interval_detail(_block_series(powers), _block())

    drawn = _y_values(figure.axes[0].lines[0])
    assert math.isnan(drawn[1])


def test_an_unrecorded_channel_keeps_its_panel_with_a_note() -> None:
    """Dropping the panel would hide that the athlete rode without the
    sensor; an empty panel with a note keeps the absence visible."""
    figure = plot_interval_detail(_block_series([200, 210]), _block())

    cadence_axes = figure.axes[2]
    assert not cadence_axes.lines
    assert _note_texts(cadence_axes) == ["Keine Trittfrequenz aufgezeichnet"]


def test_a_recorded_channel_gets_no_note() -> None:
    figure = plot_interval_detail(
        _block_series([200, 210], cadences=[90, 92]), _block()
    )

    assert _note_texts(figure.axes[2]) == []


def test_heart_rate_and_cadence_are_drawn_on_their_own_panels() -> None:
    figure = plot_interval_detail(
        _block_series([200, 210], heart_rates=[150, 155], cadences=[90, 92]), _block()
    )

    assert _y_values(figure.axes[1].lines[0]) == [150.0, 155.0]
    assert _y_values(figure.axes[2].lines[0]) == [90.0, 92.0]


def test_the_time_axis_starts_at_zero_for_every_block() -> None:
    """Blocks are compared by opening them one after the other, which only
    works if they share a scale rather than each starting at its own
    offset into the ride."""
    figure = plot_interval_detail(_block_series([200, 210, 220]), _block())

    assert _x_values(figure.axes[0].lines[0])[0] == 0.0


def test_rejects_an_empty_series() -> None:
    with pytest.raises(deal.PreContractError):
        plot_interval_detail(_block_series([]), _block())


def test_rejects_a_non_positive_target() -> None:
    with pytest.raises(deal.PreContractError):
        plot_interval_detail(_block_series([200]), _block(), target_power_w=0)
