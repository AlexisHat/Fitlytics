"""Tests for plots.gps_map."""

from datetime import UTC, datetime, timedelta

from models import RecordPoint
from plots.gps_map import METRICS, MetricKey, available_metrics
from plots.series import build_time_series

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    cadence: int | None = None,
    speed_ms: float | None = None,
    grade_pct: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        cadence=cadence,
        speed_ms=speed_ms,
        grade_pct=grade_pct,
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
