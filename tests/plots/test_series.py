"""Tests for plots.series."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from models import RecordPoint
from plots.series import available_channels, build_time_series

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    cadence: int | None = None,
    distance_m: float | None = None,
    speed_ms: float | None = None,
    altitude_m: float | None = None,
    grade_pct: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        cadence=cadence,
        distance_m=distance_m,
        speed_ms=speed_ms,
        altitude_m=altitude_m,
        grade_pct=grade_pct,
    )


def test_build_time_series_keeps_one_row_per_record() -> None:
    series = build_time_series([_point(0, heart_rate=140), _point(1, heart_rate=141)])

    assert len(series) == 2


def test_build_time_series_elapsed_s_starts_at_zero_and_is_monotonic() -> None:
    series = build_time_series(
        [_point(0), _point(1), _point(5)],
    )

    assert series["elapsed_s"].to_list() == [0.0, 1.0, 5.0]


def test_build_time_series_converts_distance_to_km() -> None:
    series = build_time_series([_point(0, distance_m=1500.0)])

    assert series["distance_km"].to_list() == [1.5]


def test_build_time_series_converts_speed_to_kmh() -> None:
    series = build_time_series([_point(0, speed_ms=10.0)])

    assert series["speed_kmh"].to_list() == pytest.approx([36.0])


def test_build_time_series_altitude_relative_starts_at_zero() -> None:
    series = build_time_series(
        [
            _point(0, altitude_m=38.0),
            _point(1, altitude_m=42.0),
            _point(2, altitude_m=35.0),
        ]
    )

    assert series["altitude_relative_m"].to_list() == pytest.approx([0.0, 4.0, -3.0])


def test_build_time_series_altitude_relative_uses_first_non_null_as_baseline() -> None:
    """A device may take a moment to lock the barometer at the very start."""
    series = build_time_series(
        [
            _point(0, altitude_m=None),
            _point(1, altitude_m=40.0),
            _point(2, altitude_m=45.0),
        ]
    )

    assert series["altitude_relative_m"].to_list() == pytest.approx([None, 0.0, 5.0])


def test_build_time_series_rejects_empty_records() -> None:
    with pytest.raises(deal.PreContractError):
        build_time_series([])


def test_build_time_series_rejects_records_out_of_order() -> None:
    with pytest.raises(deal.PreContractError):
        build_time_series([_point(5), _point(0)])


def test_power_rolling_30s_does_not_blend_across_a_pause() -> None:
    """A pause must not smear post-pause power into the pre-pause average."""
    before_pause = [_point(i, power=100) for i in range(30)]
    after_pause = [_point(30 + 60 + i, power=300) for i in range(3)]

    series = build_time_series(before_pause + after_pause)

    assert series["power_rolling_30s"].to_list()[-1] == pytest.approx(300.0)


def test_power_rolling_30s_averages_within_the_window() -> None:
    records = [_point(i, power=100) for i in range(29)] + [_point(29, power=200)]

    series = build_time_series(records)

    last_mean = series["power_rolling_30s"].to_list()[-1]
    assert last_mean == pytest.approx((29 * 100 + 200) / 30)


def test_available_channels_reports_only_measured_columns() -> None:
    series = build_time_series([_point(0, heart_rate=140)])

    assert available_channels(series) == frozenset({"heart_rate"})


def test_available_channels_is_empty_without_any_measurement() -> None:
    series = build_time_series([_point(0)])

    assert available_channels(series) == frozenset()


def test_available_channels_detects_every_supported_channel() -> None:
    series = build_time_series(
        [
            _point(
                0,
                heart_rate=140,
                power=200,
                cadence=90,
                distance_m=10.0,
                speed_ms=5.0,
                altitude_m=100.0,
                grade_pct=1.5,
            )
        ]
    )

    assert available_channels(series) == frozenset(
        {
            "heart_rate",
            "power",
            "cadence",
            "speed_kmh",
            "altitude_m",
            "grade_pct",
            "distance_km",
        }
    )
