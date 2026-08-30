"""Tests for plots.distance."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import deal
import polars as pl
import pytest

from errors import AnalysisError
from models import RecordPoint
from plots.distance import (
    _integrate_distance_km,
    _strictly_increasing_by_distance,
    prepare_distance_axis,
)
from plots.series import build_time_series

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _point(
    offset_s: int,
    distance_m: float | None = None,
    speed_ms: float | None = None,
    heart_rate: int | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        distance_m=distance_m,
        speed_ms=speed_ms,
        heart_rate=heart_rate,
    )


def test_integrate_distance_km_accumulates_speed_over_time() -> None:
    series = pl.DataFrame(
        {"elapsed_s": [0.0, 1.0, 2.0], "speed_kmh": [0.0, 36.0, 36.0]}
    )

    assert _integrate_distance_km(series).to_list() == pytest.approx([0.0, 0.01, 0.02])


def test_integrate_distance_km_treats_a_missing_speed_as_no_movement() -> None:
    series = pl.DataFrame(
        {"elapsed_s": [0.0, 1.0, 2.0], "speed_kmh": [36.0, None, 36.0]}
    )

    assert _integrate_distance_km(series).to_list() == pytest.approx([0.0, 0.0, 0.01])


def test_strictly_increasing_by_distance_collapses_a_standstill() -> None:
    series = pl.DataFrame({"distance_km": [0.0, 1.0, 1.0, 1.0, 2.0]})

    assert _strictly_increasing_by_distance(series)["distance_km"].to_list() == [
        0.0,
        1.0,
        2.0,
    ]


def test_strictly_increasing_by_distance_clamps_a_gps_regression() -> None:
    series = pl.DataFrame({"distance_km": [0.0, 1.0, 0.9, 1.5, 2.0]})

    assert _strictly_increasing_by_distance(series)["distance_km"].to_list() == [
        0.0,
        1.0,
        1.5,
        2.0,
    ]


def test_strictly_increasing_by_distance_rejects_an_empty_series() -> None:
    with pytest.raises(deal.PreContractError):
        _strictly_increasing_by_distance(pl.DataFrame({"distance_km": []}))


def test_prepare_distance_axis_uses_the_recorded_distance_when_present() -> None:
    records = [_point(i, distance_m=float(i * 5)) for i in range(3)]

    result = prepare_distance_axis(build_time_series(records))

    assert result["distance_km"].to_list() == pytest.approx([0.0, 0.005, 0.01])


def test_prepare_distance_axis_falls_back_to_integrating_speed() -> None:
    records = [_point(i, speed_ms=10.0) for i in range(3)]

    result = prepare_distance_axis(build_time_series(records))

    assert result["distance_km"].to_list()[-1] > 0.0


def test_prepare_distance_axis_forward_fills_a_mid_ride_dropout() -> None:
    """A brief GPS dropout must not reset distance to zero mid-ride."""
    records = [
        _point(0, distance_m=0.0),
        _point(1, distance_m=10.0),
        _point(2, distance_m=None),
        _point(3, distance_m=None),
        _point(4, distance_m=40.0),
    ]

    result = prepare_distance_axis(build_time_series(records))

    assert result["heart_rate"].to_list().count(None) == len(result)
    # the dropout rows collapse into the last-known distance instead of
    # reappearing as a null or a drop back to zero
    assert result["distance_km"].to_list() == pytest.approx([0.0, 0.01, 0.04])


def test_prepare_distance_axis_trims_leading_rows_before_distance_is_known() -> None:
    records = [
        _point(0, distance_m=None, heart_rate=140),
        _point(1, distance_m=None, heart_rate=141),
        _point(2, distance_m=0.0, heart_rate=142),
        _point(3, distance_m=8.0, heart_rate=143),
    ]

    result = prepare_distance_axis(build_time_series(records))

    assert result["heart_rate"].to_list() == [142, 143]


def test_prepare_distance_axis_result_is_strictly_increasing() -> None:
    records = (
        [_point(i, distance_m=float(i)) for i in range(5)]
        + [_point(5 + i, distance_m=5.0) for i in range(20)]  # a long red light
        + [_point(25 + i, distance_m=5.0 + i) for i in range(1, 5)]
    )

    result = prepare_distance_axis(build_time_series(records))

    distances = result["distance_km"].to_list()
    assert all(a < b for a, b in pairwise(distances))


def test_prepare_distance_axis_rejects_a_workout_with_neither_distance_nor_speed() -> (
    None
):
    records = [_point(0, heart_rate=140), _point(1, heart_rate=141)]

    with pytest.raises(AnalysisError):
        prepare_distance_axis(build_time_series(records))


def test_prepare_distance_axis_rejects_a_ride_that_never_moves() -> None:
    records = [_point(i, speed_ms=0.0, heart_rate=140) for i in range(5)]

    with pytest.raises(AnalysisError):
        prepare_distance_axis(build_time_series(records))
