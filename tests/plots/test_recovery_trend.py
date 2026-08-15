"""Tests for plots.recovery_trend."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import cast

import deal
import pytest
from matplotlib.figure import Figure

from models import RecoveryDay
from plots.recovery_trend import plot_recovery_trend

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
