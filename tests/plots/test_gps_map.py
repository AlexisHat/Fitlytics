"""Tests for plots.gps_map."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from errors import AnalysisError
from models import RecordPoint
from plots.gps_map import METRICS, MetricKey, available_metrics, build_gps_map_figure
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
    _point(0, latitude=51.05, longitude=6.85),
    _point(1, latitude=51.06, longitude=6.86),
    _point(2, latitude=51.07, longitude=6.87),
]


def test_build_gps_map_figure_rejects_a_workout_without_gps() -> None:
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records))


def test_build_gps_map_figure_rejects_a_single_gps_fix() -> None:
    records = [_point(0, latitude=51.05, longitude=6.85), _point(1, heart_rate=140)]

    with pytest.raises(AnalysisError):
        build_gps_map_figure(build_time_series(records))


def test_build_gps_map_figure_draws_one_line_trace() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS))

    assert len(fig.data) == 1
    assert fig.data[0].mode == "lines"


def test_build_gps_map_figure_bounds_match_the_track_extent() -> None:
    fig = build_gps_map_figure(build_time_series(_TRACK_RECORDS))

    bounds = fig.layout.map.bounds
    assert (bounds.west, bounds.east, bounds.south, bounds.north) == pytest.approx(
        (6.85, 6.87, 51.05, 51.07)
    )


def test_build_gps_map_figure_leaves_a_gap_at_a_missing_fix() -> None:
    """A GPS dropout mid-ride (e.g. a tunnel) must break the line, not bridge it."""
    records = [
        _point(0, latitude=51.05, longitude=6.85),
        _point(1, heart_rate=140),
        _point(2, latitude=51.07, longitude=6.87),
    ]

    fig = build_gps_map_figure(build_time_series(records))

    assert math.isnan(fig.data[0].lat[1])
    assert fig.data[0].connectgaps is False
