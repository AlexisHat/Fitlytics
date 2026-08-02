"""Tests for plots.timeline."""

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from errors import AnalysisError
from models import RecordPoint
from plots.series import build_time_series
from plots.timeline import XAxisMode, build_timeline_figure

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    speed_ms: float | None = None,
    altitude_m: float | None = None,
    distance_m: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        speed_ms=speed_ms,
        altitude_m=altitude_m,
        distance_m=distance_m,
    )


_FULL_RECORDS = [
    _point(
        0, heart_rate=140, power=200, speed_ms=8.0, altitude_m=100.0, distance_m=0.0
    ),
    _point(
        1, heart_rate=141, power=None, speed_ms=8.5, altitude_m=101.0, distance_m=8.0
    ),
    _point(
        2, heart_rate=142, power=220, speed_ms=9.0, altitude_m=102.0, distance_m=17.0
    ),
]


def test_build_timeline_figure_has_one_trace_per_panel_plus_raw_power() -> None:
    """4 panels, but the power one also draws a faint raw trace behind it."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert len(fig.data) == 5


def test_build_timeline_figure_orders_panels_altitude_power_hr_speed() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert [trace.name for trace in fig.data] == [
        "Höhe (m)",
        "Leistung (W)",
        "Leistung (W)",
        "Herzfrequenz (bpm)",
        "Geschwindigkeit (km/h)",
    ]


def test_build_timeline_figure_assigns_each_panel_its_own_yaxis() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert [trace.yaxis for trace in fig.data] == ["y", "y2", "y2", "y3", "y4"]


def test_build_timeline_figure_puts_every_panel_on_one_shared_xaxis() -> None:
    """A single real x-axis, not four range-matched ones, is what makes the
    hover crosshair span every panel instead of just the one under the
    cursor."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert [trace.xaxis for trace in fig.data] == ["x"] * 5
    assert "xaxis2" not in fig.layout
    assert fig.layout.xaxis.anchor == "y4"


def test_build_timeline_figure_leaves_a_gap_at_a_missing_raw_sample() -> None:
    """A single dropout must break the raw line, not be silently skipped."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    raw_power_trace = fig.data[1]
    assert math.isnan(raw_power_trace.y[1])


def test_build_timeline_figure_shows_the_raw_power_reading_in_hover() -> None:
    """The exact instantaneous watt value is more useful to point at than a
    30s average, even though the smoothed line is what stays visible on top."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    raw_power_trace = fig.data[1]
    assert raw_power_trace.hovertemplate == "Leistung (W): %{y:.0f}<extra></extra>"
    assert raw_power_trace.showlegend is False
    assert raw_power_trace.opacity == pytest.approx(0.35)


def test_build_timeline_figure_silences_hover_on_the_smoothed_power_line() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    rolling_power_trace = fig.data[2]
    assert rolling_power_trace.hoverinfo == "skip"


def test_build_timeline_figure_hides_the_legend() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.showlegend is False


def test_build_timeline_figure_gives_altitude_the_smallest_panel() -> None:
    """Altitude is context, power/heart rate carry the most information."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    def _panel_height(domain: tuple[float, float]) -> float:
        return domain[1] - domain[0]

    altitude_height = _panel_height(fig.layout.yaxis.domain)
    power_height = _panel_height(fig.layout.yaxis2.domain)
    assert altitude_height < power_height


def test_build_timeline_figure_fills_the_altitude_panel_as_a_terrain_profile() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.data[0].fill == "tozeroy"
    assert fig.data[2].fill is None


def test_build_timeline_figure_drops_panels_without_data() -> None:
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    fig = build_timeline_figure(build_time_series(records))

    assert [trace.name for trace in fig.data] == ["Herzfrequenz (bpm)"]


def test_build_timeline_figure_rejects_a_series_with_no_chartable_channel() -> None:
    records = [_point(0), _point(1)]

    with pytest.raises(AnalysisError):
        build_timeline_figure(build_time_series(records))


def test_build_timeline_figure_uses_unified_hover() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.hovermode == "x unified"


def test_build_timeline_figure_shows_a_crosshair_spanning_all_panels() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.showspikes is True
    assert fig.layout.xaxis.spikemode == "across"
    for yaxis in (fig.layout.yaxis, fig.layout.yaxis2, fig.layout.yaxis3):
        assert yaxis.showspikes is True
        assert yaxis.spikemode == "toaxis"


def test_build_timeline_figure_shows_a_rangeslider() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.rangeslider.visible is True


def test_build_timeline_figure_stacks_panel_domains_top_to_bottom() -> None:
    """Panel i+1 (further down the figure) must not overlap panel i above it."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    domains = [
        fig.layout.yaxis.domain,
        fig.layout.yaxis2.domain,
        fig.layout.yaxis3.domain,
        fig.layout.yaxis4.domain,
    ]
    for (low, _), (_, next_high) in pairwise(domains):
        assert next_high <= low


def test_build_timeline_figure_formats_the_time_axis_as_a_clock() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.type == "date"
    assert fig.layout.xaxis.tickformat == "%H:%M:%S"


def test_build_timeline_figure_labels_the_altitude_hover_in_german() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    altitude_trace = fig.data[0]
    assert altitude_trace.hovertemplate == "Höhe (m): %{y:.0f}<extra></extra>"


def test_build_timeline_figure_gives_speed_one_decimal_in_the_hover() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    speed_trace = fig.data[4]
    assert (
        speed_trace.hovertemplate == "Geschwindigkeit (km/h): %{y:.1f}<extra></extra>"
    )


def test_build_timeline_figure_defaults_to_the_time_axis() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.type == "date"
    assert fig.layout.xaxis.title.text == "Zeit"


def test_build_timeline_figure_switches_to_the_distance_axis() -> None:
    fig = build_timeline_figure(
        build_time_series(_FULL_RECORDS), x_axis=XAxisMode.DISTANCE
    )

    assert fig.layout.xaxis.type == "linear"
    assert fig.layout.xaxis.title.text == "Distanz (km)"
    assert fig.data[0].x.tolist() == pytest.approx([0.0, 0.008, 0.017])


def test_build_timeline_figure_rejects_distance_axis_without_distance() -> None:
    records = [
        _point(0, heart_rate=140, distance_m=None),
        _point(1, heart_rate=141, distance_m=None),
    ]

    with pytest.raises(AnalysisError):
        build_timeline_figure(build_time_series(records), x_axis=XAxisMode.DISTANCE)
