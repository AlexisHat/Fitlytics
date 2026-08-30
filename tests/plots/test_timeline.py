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


def test_build_timeline_figure_orders_panels_power_hr_speed_elevation() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    titles = [annotation.text for annotation in fig.layout.annotations]
    assert titles == [
        "Leistung (W)",
        "Herzfrequenz (bpm)",
        "Geschwindigkeit (km/h)",
        "Höhe (m)",
    ]


def test_build_timeline_figure_plots_against_cumulative_distance() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.data[0].x.tolist() == pytest.approx([0.0, 0.008, 0.017])
    assert fig.layout.xaxis.type == "linear"


def test_build_timeline_figure_puts_power_hr_speed_on_one_shared_xaxis() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    top_group = [trace for trace in fig.data if trace.name != "Höhe (m)"]
    assert all(trace.xaxis in (None, "x") for trace in top_group)


def test_build_timeline_figure_puts_elevation_on_its_own_matched_xaxis() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    elevation_trace = next(trace for trace in fig.data if trace.name == "Höhe (m)")
    assert elevation_trace.xaxis == "x2"
    assert fig.layout.xaxis2.matches == "x"


def test_build_timeline_figure_leaves_a_gap_at_a_missing_raw_sample() -> None:
    """A single dropout must break the raw line, not be silently skipped."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    raw_power_trace = fig.data[0]
    assert math.isnan(raw_power_trace.y[1])


def test_build_timeline_figure_shows_the_raw_power_reading_in_hover() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert "Leistung (W): %{y:.0f}" in fig.data[0].hovertemplate


def test_build_timeline_figure_silences_hover_on_the_smoothed_power_line() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.data[1].hoverinfo == "skip"


def test_build_timeline_figure_hides_the_legend() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.showlegend is False


def test_build_timeline_figure_gives_elevation_the_smallest_panel() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    power_span = fig.layout.yaxis.domain[1] - fig.layout.yaxis.domain[0]
    elevation_span = fig.layout.yaxis4.domain[1] - fig.layout.yaxis4.domain[0]
    assert elevation_span < power_span


def test_build_timeline_figure_fills_the_elevation_panel_as_a_terrain_profile() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    elevation_trace = next(trace for trace in fig.data if trace.name == "Höhe (m)")
    assert elevation_trace.fill == "tozeroy"


def test_build_timeline_figure_plots_elevation_as_absolute_altitude() -> None:
    """Not relative-to-start: the y-values are the recorded altitudes themselves."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    elevation_trace = next(trace for trace in fig.data if trace.name == "Höhe (m)")
    assert min(y for y in elevation_trace.y if y is not None) > 0


def test_build_timeline_figure_drops_panels_without_data() -> None:
    records = [
        _point(0, heart_rate=140, distance_m=0.0),
        _point(1, heart_rate=141, distance_m=8.0),
    ]

    fig = build_timeline_figure(build_time_series(records))

    assert len(fig.data) == 1
    assert fig.layout.annotations[0].text == "Herzfrequenz (bpm)"


def test_build_timeline_figure_rejects_a_series_with_no_chartable_channel() -> None:
    records = [_point(0), _point(1)]

    with pytest.raises(AnalysisError):
        build_timeline_figure(build_time_series(records))


def test_build_timeline_figure_uses_unified_hover() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.hovermode == "x unified"


def test_build_timeline_figure_shows_a_crosshair_within_the_shared_group() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.showspikes is True
    assert fig.layout.yaxis.showspikes is True
    assert fig.layout.yaxis2.showspikes is True


def test_build_timeline_figure_keeps_the_slider_to_exactly_one_trace() -> None:
    """The native rangeslider mirrors every trace on its host axis with no
    opt-out, so elevation sits on its own axis specifically to keep the
    slider to a single trace — this asserts that split held."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    on_elevation_axis = [trace for trace in fig.data if trace.xaxis == "x2"]
    assert len(on_elevation_axis) == 1


def test_build_timeline_figure_shows_a_rangeslider_on_the_elevation_axis() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis2.rangeslider.visible is True
    assert fig.layout.xaxis.rangeslider.visible in (False, None)


def test_build_timeline_figure_hides_ticks_on_the_shared_top_axis() -> None:
    """The visible distance ticks live on the elevation axis instead, right
    above the rangeslider — showing them twice would be redundant."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.xaxis.showticklabels is False
    assert fig.layout.xaxis2.title.text == "Distanz (km)"


def test_build_timeline_figure_shows_visible_ticks_without_an_elevation_panel() -> None:
    records = [
        _point(0, heart_rate=140, distance_m=0.0),
        _point(1, heart_rate=141, distance_m=8.0),
    ]

    fig = build_timeline_figure(build_time_series(records))

    assert fig.layout.xaxis.showticklabels is not False
    assert fig.layout.xaxis.title.text == "Distanz (km)"
    assert not any(trace.xaxis == "x2" for trace in fig.data)


def test_build_timeline_figure_stacks_panel_domains_top_to_bottom() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    assert fig.layout.yaxis.domain[0] > fig.layout.yaxis2.domain[1]
    assert fig.layout.yaxis2.domain[0] > fig.layout.yaxis3.domain[1]


def test_build_timeline_figure_labels_the_elevation_hover_in_german() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    elevation_trace = next(trace for trace in fig.data if trace.name == "Höhe (m)")
    assert "Höhe (m): %{y:.0f}" in elevation_trace.hovertemplate


def test_build_timeline_figure_gives_speed_one_decimal_in_the_hover() -> None:
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    speed_trace = next(
        trace for trace in fig.data if trace.name == "Geschwindigkeit (km/h)"
    )
    assert "%{y:.1f}" in speed_trace.hovertemplate


def test_build_timeline_figure_shows_elapsed_time_once_per_hover_group() -> None:
    """The elapsed clock appears exactly once in the shared-axis group (on
    its first rendered panel) and once on elevation's own, separate group —
    never repeated across every trace in a group."""
    fig = build_timeline_figure(build_time_series(_FULL_RECORDS))

    top_group_time_lines = sum(
        1
        for trace in fig.data
        if trace.xaxis in (None, "x")
        and trace.hovertemplate
        and "Zeit:" in trace.hovertemplate
    )
    elevation_time_lines = sum(
        1
        for trace in fig.data
        if trace.xaxis == "x2"
        and trace.hovertemplate
        and "Zeit:" in trace.hovertemplate
    )
    assert top_group_time_lines == 1
    assert elevation_time_lines == 1


def test_build_timeline_figure_trims_a_staggered_sensor_start() -> None:
    """A slow GPS/barometer lock must not leave a blank lead-in on the chart."""
    records = [
        _point(0, heart_rate=140, power=200, distance_m=0.0),
        _point(1, heart_rate=141, power=205, distance_m=8.0),
        _point(2, heart_rate=142, power=210, altitude_m=100.0, distance_m=17.0),
        _point(3, heart_rate=143, power=215, altitude_m=101.0, distance_m=25.0),
    ]

    fig = build_timeline_figure(build_time_series(records))

    # a 15s trailing rolling median: the second point still has both
    # samples in its window, so it comes out as their average (100.5),
    # which incidentally also proves the smoothing is actually applied
    elevation_trace = next(trace for trace in fig.data if trace.name == "Höhe (m)")
    assert elevation_trace.y.tolist() == pytest.approx([100.0, 100.5])


def test_build_timeline_figure_rejects_a_workout_without_distance_or_speed() -> None:
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    with pytest.raises(AnalysisError):
        build_timeline_figure(build_time_series(records))


def test_build_timeline_figure_handles_elevation_as_the_only_panel() -> None:
    """No power, heart rate or speed at all — elevation becomes the figure's
    only panel and must own the plain "y" axis id, not an invalid "y1"."""
    records = [
        _point(0, altitude_m=100.0, distance_m=0.0),
        _point(1, altitude_m=101.0, distance_m=8.0),
        _point(2, altitude_m=102.0, distance_m=17.0),
    ]

    fig = build_timeline_figure(build_time_series(records))

    assert len(fig.data) == 1
    assert fig.data[0].yaxis in (None, "y")
    assert fig.layout.yaxis.domain is not None
    assert fig.layout.xaxis2.rangeslider.visible is True
