"""Tests for plots.timeline."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from errors import AnalysisError
from models import RecordPoint
from plots.series import build_time_series
from plots.timeline import build_timeline_figure

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    speed_ms: float | None = None,
    altitude_m: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        speed_ms=speed_ms,
        altitude_m=altitude_m,
    )


_FULL_RECORDS = [
    _point(0, heart_rate=140, power=200, speed_ms=8.0, altitude_m=100.0),
    _point(1, heart_rate=141, power=None, speed_ms=8.5, altitude_m=101.0),
    _point(2, heart_rate=142, power=220, speed_ms=9.0, altitude_m=102.0),
]


def test_build_timeline_figure_has_one_trace_per_available_panel() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert len(fig.data) == 4


def test_build_timeline_figure_orders_panels_altitude_power_hr_speed() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert [trace.name for trace in fig.data] == [
        "Höhe (m)",
        "Leistung (W)",
        "Herzfrequenz (bpm)",
        "Geschwindigkeit (km/h)",
    ]


def test_build_timeline_figure_assigns_each_panel_its_own_row() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert [trace.xaxis for trace in fig.data] == ["x", "x2", "x3", "x4"]
    assert [trace.yaxis for trace in fig.data] == ["y", "y2", "y3", "y4"]


def test_build_timeline_figure_couples_every_xaxis_to_the_bottom_panel() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.matches == "x4"
    assert fig.layout.xaxis2.matches == "x4"
    assert fig.layout.xaxis3.matches == "x4"


def test_build_timeline_figure_leaves_a_gap_at_a_missing_sample() -> None:
    """A single dropout must break the line, not be silently skipped."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    power_trace = fig.data[1]
    assert math.isnan(power_trace.y[1])


def test_build_timeline_figure_fills_the_altitude_panel_as_a_terrain_profile() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.data[0].fill == "tozeroy"
    assert fig.data[1].fill is None


def test_build_timeline_figure_drops_panels_without_data() -> None:
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    fig = build_timeline_figure(build_time_series(records))

    assert [trace.name for trace in fig.data] == ["Herzfrequenz (bpm)"]


def test_build_timeline_figure_rejects_a_series_with_no_chartable_channel() -> None:
    records = [_point(0), _point(1)]

    with pytest.raises(AnalysisError):
        build_timeline_figure(build_time_series(records))
