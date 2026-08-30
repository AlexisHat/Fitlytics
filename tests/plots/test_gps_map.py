"""Tests for plots.gps_map."""

import math
from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest

from errors import AnalysisError
from models import RecordPoint
from plots.gps_map import (
    METRICS,
    MetricKey,
    _fitting_zoom,
    _mercator_y,
    available_metrics,
    build_gps_map_figure,
)
from plots.series import build_time_series

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    cadence: int | None = None,
    speed_ms: float | None = None,
    grade_pct: float | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    distance_m: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        cadence=cadence,
        speed_ms=speed_ms,
        grade_pct=grade_pct,
        latitude=latitude,
        longitude=longitude,
        distance_m=distance_m,
    )


def _series_with_track() -> pl.DataFrame:
    """A two-fix track spanning 51.05-51.06 N and 6.85-6.86 E."""
    return build_time_series(
        [
            _point(0, heart_rate=140, latitude=51.05, longitude=6.85),
            _point(1, heart_rate=150, latitude=51.06, longitude=6.86),
        ]
    )


def test_available_metrics_reports_only_measured_metrics() -> None:
    series = build_time_series([_point(0, heart_rate=140), _point(1, heart_rate=141)])

    assert available_metrics(series) == (MetricKey.HEART_RATE,)


def test_available_metrics_is_empty_without_any_metric() -> None:
    series = build_time_series([_point(0), _point(1)])

    assert available_metrics(series) == ()


def test_available_metrics_detects_every_supported_metric() -> None:
    records = [
        _point(0, heart_rate=140, power=200, cadence=90, speed_ms=8.0, grade_pct=2.5)
    ]

    series = build_time_series(records)

    assert available_metrics(series) == (
        MetricKey.POWER,
        MetricKey.SPEED,
        MetricKey.HEART_RATE,
        MetricKey.GRADE,
        MetricKey.CADENCE,
    )


def test_metrics_registry_columns_exist_in_the_time_series() -> None:
    """Every registered metric must point at a column build_time_series emits."""
    series = build_time_series([_point(0, heart_rate=140)])

    for spec in METRICS.values():
        assert spec.column in series.columns


_TRACK_RECORDS = [
    _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
    _point(1, latitude=51.06, longitude=6.86, heart_rate=160),
    _point(2, latitude=51.07, longitude=6.87, heart_rate=150),
]


def test_build_gps_map_figure_rejects_a_workout_without_gps() -> None:
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)


def test_build_gps_map_figure_rejects_a_single_gps_fix() -> None:
    records = [_point(0, latitude=51.05, longitude=6.85), _point(1, heart_rate=140)]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)


def test_build_gps_map_figure_rejects_a_metric_without_any_data() -> None:
    records = [
        _point(0, latitude=51.05, longitude=6.85),
        _point(1, latitude=51.06, longitude=6.86),
    ]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records), MetricKey.POWER)


def test_build_gps_map_figure_draws_a_line_and_a_marker_trace() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    assert len(fig.data) == 2
    assert fig.data[0].mode == "lines"
    assert fig.data[1].mode == "markers"


def test_build_gps_map_figure_centres_on_the_track_extent() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    centre = fig.layout.map.center
    assert (centre.lon, centre.lat) == pytest.approx((6.86, 51.06))


def test_build_gps_map_figure_leaves_a_gap_at_a_missing_fix() -> None:
    """A GPS dropout mid-ride (e.g. a tunnel) must break the line, not bridge it."""
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
        _point(1, heart_rate=145),
        _point(2, latitude=51.07, longitude=6.87, heart_rate=150),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    assert math.isnan(fig.data[0].lat[1])
    assert fig.data[0].connectgaps is False


def test_build_gps_map_figure_draws_markers_in_ascending_colour_order() -> None:
    """At an overlap, the higher reading must end up drawn on top."""
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    assert fig.data[1].marker.color.tolist() == [140.0, 150.0, 160.0]


def test_build_gps_map_figure_interpolates_a_single_missing_reading() -> None:
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
        _point(1, latitude=51.06, longitude=6.86, heart_rate=None),
        _point(2, latitude=51.07, longitude=6.87, heart_rate=160),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    assert 150.0 in fig.data[1].marker.color.tolist()


def test_build_gps_map_figure_drops_a_fix_with_no_neighbouring_reading() -> None:
    """A metric missing at the very start (no earlier value to interpolate
    from) is left out of the coloured markers rather than guessed at."""
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=None),
        _point(1, latitude=51.06, longitude=6.86, heart_rate=150),
        _point(2, latitude=51.07, longitude=6.87, heart_rate=160),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    assert len(fig.data[1].marker.color) == 2


def test_build_gps_map_figure_labels_the_colorbar_with_metric_and_unit() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    assert fig.data[1].marker.colorbar.title.text == "Herzfrequenz (bpm)"


def test_build_gps_map_figure_centres_a_diverging_metric_on_zero() -> None:
    records = [
        _point(0, latitude=51.05, longitude=6.85, grade_pct=-5.0),
        _point(1, latitude=51.06, longitude=6.86, grade_pct=10.0),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.GRADE)

    assert fig.data[1].marker.cmid == 0.0


def test_build_gps_map_figure_does_not_set_cmid_for_a_sequential_metric() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    assert fig.data[1].marker.cmid is None


def test_build_gps_map_figure_hover_shows_metric_position_time_and_distance() -> None:
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140, distance_m=0.0),
        _point(65, latitude=51.06, longitude=6.86, heart_rate=150, distance_m=1500.0),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    hover_text = fig.data[1].text[1]
    assert "Herzfrequenz: 150.0 bpm" in hover_text
    assert "51.0600° N, 6.8600° O" in hover_text
    assert "Zeit: 00:01:05" in hover_text
    assert "Distanz: 1.50 km" in hover_text


def test_build_gps_map_figure_hover_is_honest_about_an_interpolated_reading() -> None:
    """The colour at an interpolated point must not be claimed as a real
    measurement in its hover text."""
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
        _point(1, latitude=51.06, longitude=6.86, heart_rate=None),
        _point(2, latitude=51.07, longitude=6.87, heart_rate=160),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    interpolated_hover = next(
        text
        for text, color in zip(fig.data[1].text, fig.data[1].marker.color, strict=True)
        if color == 150.0
    )
    assert "keine Daten" in interpolated_hover


def test_build_gps_map_figure_disables_hover_on_the_connecting_line() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS), MetricKey.HEART_RATE)

    assert fig.data[0].hoverinfo == "skip"


def test_build_gps_map_figure_accepts_exactly_two_gps_fixes() -> None:
    """Two fixes is the minimum for a track, not yet a rejection case."""
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
        _point(1, latitude=51.06, longitude=6.86, heart_rate=150),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    assert len(fig.data[1].marker.color) == 2


def test_build_gps_map_figure_handles_a_stationary_track() -> None:
    """A rider stopped at a single spot (or an indoor trainer with a stray
    GPS fix) collapses the bounding box to a single point; this must not
    raise, even though the box has no extent to fit a zoom level to."""
    records = [
        _point(0, latitude=51.05, longitude=6.85, heart_rate=140),
        _point(1, latitude=51.05, longitude=6.85, heart_rate=150),
    ]

    fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)

    centre = fig.layout.map.center
    assert (centre.lon, centre.lat) == pytest.approx((6.85, 51.05))
    assert fig.layout.map.zoom == 15.0


def test_build_gps_map_figure_rejects_a_metric_recorded_only_without_gps() -> None:
    """A metric that only has readings on rows without a GPS fix is, for
    this plot, exactly as unusable as one with no readings at all."""
    records = [
        _point(0, latitude=51.05, longitude=6.85),
        _point(1, latitude=51.06, longitude=6.86),
        _point(2, heart_rate=140),
    ]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)


def test_figure_frames_the_track_with_centre_and_zoom_not_bounds() -> None:
    """bounds is MapLibre's maxBounds, a hard limit on panning and zooming
    out — framing the track with it would make the track itself the furthest
    the rider could ever zoom out (see plots.gps_map._fitting_zoom)."""
    figure = build_gps_map_figure(_series_with_track(), MetricKey.HEART_RATE)

    assert figure.layout.map.bounds.west is None
    assert figure.layout.map.zoom is not None
    assert figure.layout.map.center.lat is not None


def test_figure_centres_the_map_on_the_tracks_midpoint() -> None:
    figure = build_gps_map_figure(_series_with_track(), MetricKey.HEART_RATE)

    assert figure.layout.map.center.lat == pytest.approx(51.055, abs=1e-6)
    assert figure.layout.map.center.lon == pytest.approx(6.855, abs=1e-6)


def test_fitting_zoom_shows_a_wider_track_further_out() -> None:
    wide = _fitting_zoom(6.8, 7.2, 51.0, 51.1)
    narrow = _fitting_zoom(6.8, 6.85, 51.0, 51.02)

    assert wide < narrow


def test_fitting_zoom_caps_a_track_without_extent() -> None:
    assert _fitting_zoom(6.85, 6.85, 51.05, 51.05) == 15.0


def test_fitting_zoom_stays_non_negative_for_a_worldwide_box() -> None:
    assert _fitting_zoom(-180.0, 180.0, -85.0, 85.0) == 0.0


def test_fitting_zoom_rejects_unordered_bounds() -> None:
    with pytest.raises(deal.PreContractError):
        _fitting_zoom(7.0, 6.8, 51.0, 51.1)


def test_mercator_y_maps_the_equator_to_the_middle() -> None:
    assert _mercator_y(0.0) == 0.5


def test_mercator_y_is_monotonic_from_north_to_south() -> None:
    assert _mercator_y(60.0) < _mercator_y(0.0) < _mercator_y(-60.0)


def test_mercator_y_clamps_the_poles_instead_of_diverging() -> None:
    assert _mercator_y(90.0) == _mercator_y(85.0)
    assert _mercator_y(-90.0) == _mercator_y(-85.0)
