"""Tests for plots.series."""

from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest

from models import RecordPoint
from plots.series import (
    available_channels,
    build_time_series,
    elevation_gain_m,
    trim_to_first_fully_measured_row,
)

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


def test_build_time_series_formats_elapsed_hms() -> None:
    series = build_time_series([_point(0), _point(65), _point(3725)])

    assert series["elapsed_hms"].to_list() == ["00:00:00", "00:01:05", "01:02:05"]


def test_build_time_series_converts_distance_to_km() -> None:
    series = build_time_series([_point(0, distance_m=1500.0)])

    assert series["distance_km"].to_list() == [1.5]


def test_build_time_series_converts_speed_to_kmh() -> None:
    series = build_time_series([_point(0, speed_ms=10.0)])

    assert series["speed_kmh"].to_list() == pytest.approx([36.0])


def test_build_time_series_keeps_altitude_absolute() -> None:
    series = build_time_series(
        [
            _point(0, altitude_m=338.0),
            _point(1, altitude_m=342.0),
            _point(2, altitude_m=335.0),
        ]
    )

    assert series["altitude_m"].to_list() == pytest.approx([338.0, 342.0, 335.0])


def test_build_time_series_smooths_altitude_with_a_rolling_median() -> None:
    """A single spurious barometer spike is dropped, not blended in."""
    records = (
        [_point(i, altitude_m=100.0) for i in range(10)]
        + [_point(10, altitude_m=500.0)]
        + [_point(11 + i, altitude_m=100.0) for i in range(10)]
    )

    series = build_time_series(records)

    assert series["altitude_smoothed_m"].to_list()[10] == pytest.approx(100.0)


def test_build_time_series_handles_a_value_past_row_100() -> None:
    """Polars' default schema inference only samples the first 100 rows of a
    list-of-dicts; a column that is None throughout that sample and only
    becomes a real float later used to crash the whole DataFrame build."""
    records = [_point(i) for i in range(120)] + [_point(120, grade_pct=41.4)]

    series = build_time_series(records)

    assert series["grade_pct"].to_list()[-1] == pytest.approx(41.4)


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


def test_trim_to_first_fully_measured_row_drops_leading_incomplete_rows() -> None:
    series = pl.DataFrame(
        {
            "elapsed_s": [0.0, 1.0, 2.0, 3.0],
            "power": [100, 110, 120, 130],
            "altitude_smoothed_m": [None, None, 5.0, 6.0],
        }
    )

    trimmed = trim_to_first_fully_measured_row(series, ["power", "altitude_smoothed_m"])

    assert trimmed["elapsed_s"].to_list() == [0.0, 1.0]
    assert trimmed["power"].to_list() == [120, 130]


def test_trim_to_first_fully_measured_row_keeps_later_gaps() -> None:
    """Only the leading gap is trimmed; a later dropout still shows as a gap."""
    series = pl.DataFrame(
        {
            "elapsed_s": [0.0, 1.0, 2.0, 3.0],
            "power": [100, 110, None, 130],
            "altitude_smoothed_m": [5.0, 6.0, 7.0, 8.0],
        }
    )

    trimmed = trim_to_first_fully_measured_row(series, ["power", "altitude_smoothed_m"])

    assert trimmed["power"].to_list() == [100, 110, None, 130]


def test_trim_to_first_fully_measured_row_keeps_series_if_never_all_present() -> None:
    series = pl.DataFrame(
        {
            "elapsed_s": [0.0, 1.0],
            "power": [100, None],
            "altitude_smoothed_m": [None, 5.0],
        }
    )

    trimmed = trim_to_first_fully_measured_row(series, ["power", "altitude_smoothed_m"])

    assert trimmed["elapsed_s"].to_list() == [0.0, 1.0]


def test_elevation_gain_m_sums_only_the_positive_deltas() -> None:
    assert elevation_gain_m([100.0, 105.0, 102.0, 110.0]) == pytest.approx(13.0)


def test_elevation_gain_m_skips_null_readings_without_treating_them_as_a_drop() -> None:
    assert elevation_gain_m([100.0, None, 110.0]) == pytest.approx(10.0)


def test_elevation_gain_m_is_zero_for_a_pure_descent() -> None:
    assert elevation_gain_m([200.0, 150.0, 100.0]) == 0.0


def test_elevation_gain_m_needs_at_least_two_readings() -> None:
    assert elevation_gain_m([100.0]) is None
    assert elevation_gain_m([]) is None
