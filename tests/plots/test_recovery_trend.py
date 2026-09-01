"""Tests for plots.recovery_trend."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import cast

import deal
import pytest
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure

from models import RecoveryDay
from plots.intensity import intensity_color
from plots.recovery_trend import plot_recovery_trend, workout_marker_colors

START = date(2026, 7, 1)


def _days(
    hrv: Sequence[float | None], resting_hr: Sequence[int | None] | None = None
) -> list[RecoveryDay]:
    resting_hr = resting_hr if resting_hr is not None else [55] * len(hrv)
    return [
        RecoveryDay(
            date=START + timedelta(days=offset),
            cycle_start=datetime.combine(
                START + timedelta(days=offset), datetime.min.time(), tzinfo=UTC
            ),
            hrv_ms=value,
            resting_hr=rate,
        )
        for offset, (value, rate) in enumerate(zip(hrv, resting_hr, strict=True))
    ]


def _line_y(figure: Figure, axis: int, line: int) -> list[float]:
    values = cast(Sequence[float], figure.axes[axis].lines[line].get_ydata())
    return [float(value) for value in values]


def test_plot_draws_one_panel_per_measure() -> None:
    figure = plot_recovery_trend(_days([90.0] * 10))

    assert len(figure.axes) == 2


def test_plot_draws_the_daily_values_and_the_trend_in_each_panel() -> None:
    figure = plot_recovery_trend(_days([90.0] * 10))

    assert len(figure.axes[0].lines) == 2
    assert len(figure.axes[1].lines) == 2


def test_plot_keeps_the_daily_values_unsmoothed() -> None:
    hrv = [50.0] * 6 + [200.0] + [50.0] * 6
    figure = plot_recovery_trend(_days(hrv))

    assert max(_line_y(figure, 0, 0)) == 200.0


def test_plot_trend_line_damps_what_the_daily_line_shows() -> None:
    """The two lines must differ, or the trend adds nothing to the chart."""
    hrv = [50.0] * 6 + [200.0] + [50.0] * 6
    figure = plot_recovery_trend(_days(hrv))

    assert max(_line_y(figure, 0, 1)) < max(_line_y(figure, 0, 0))


def test_plot_handles_a_day_without_measurements() -> None:
    """The last cycle of an export often has no scores yet; it is still a
    real day on the time axis."""
    figure = plot_recovery_trend(_days([90.0, None, 95.0], [55, None, 56]))

    assert len(figure.axes) == 2


def test_plot_handles_a_history_without_any_hrv_at_all() -> None:
    figure = plot_recovery_trend(_days([None, None, None], [55, 56, 57]))

    assert len(figure.axes) == 2


def test_plot_rejects_an_empty_history() -> None:
    with pytest.raises(deal.PreContractError):
        plot_recovery_trend([])


def _marker_colors(figure: Figure) -> list[str]:
    """Colours of the workout markers, which are the lines drawn behind the curves."""
    return [
        str(line.get_color()) for line in figure.axes[0].lines if line.get_zorder() == 0
    ]


def test_no_workout_loads_draws_no_markers() -> None:
    figure = plot_recovery_trend(_days([90.0] * 5))

    assert _marker_colors(figure) == []


def test_every_workout_day_in_span_gets_a_marker_on_both_panels() -> None:
    loads = {START: 100.0, START + timedelta(days=2): 60.0}

    figure = plot_recovery_trend(_days([90.0] * 5), loads)

    for axes in figure.axes:
        assert len([line for line in axes.lines if line.get_zorder() == 0]) == 2


def test_harder_day_is_marked_in_a_redder_colour_than_an_easy_one() -> None:
    easy, hard = START, START + timedelta(days=1)

    figure = plot_recovery_trend(_days([90.0] * 5), {easy: 25.0, hard: 250.0})
    easy_color, hard_color = _marker_colors(figure)
    easy_red, easy_green, _ = to_rgb(easy_color)
    hard_red, hard_green, _ = to_rgb(hard_color)

    assert hard_red > easy_red
    assert hard_green < easy_green


def test_a_day_at_or_above_the_reference_load_is_marked_in_the_scale_end() -> None:
    figure = plot_recovery_trend(_days([90.0] * 5), {START: 400.0})

    assert _marker_colors(figure) == [intensity_color(100)]


def test_workout_days_outside_the_shown_span_are_left_out() -> None:
    loads = {START - timedelta(days=10): 100.0, START + timedelta(days=99): 100.0}

    figure = plot_recovery_trend(_days([90.0] * 5), loads)

    assert _marker_colors(figure) == []


def test_title_mentions_the_markers_only_when_there_are_some() -> None:
    without = plot_recovery_trend(_days([90.0] * 5))
    with_markers = plot_recovery_trend(_days([90.0] * 5), {START: 100.0})

    assert "Trainingstagen" not in without.axes[0].get_title()
    assert "Trainingstagen" in with_markers.axes[0].get_title()


def test_workout_marker_colors_is_ordered_by_date_whatever_the_input_order() -> None:
    later, earlier = START + timedelta(days=3), START

    pairs = workout_marker_colors({later: 100.0, earlier: 100.0})

    assert [day for day, _ in pairs] == [earlier, later]


def test_workout_marker_colors_gives_no_pairs_for_no_training_days() -> None:
    assert workout_marker_colors({}) == []
