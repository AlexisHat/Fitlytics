"""Tests for analysis.workout."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from analysis import compute_workout_metrics
from analysis.workout import _split_elapsed_and_moving_time, _work_kj, vam
from models import RecordPoint, Workout

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(
    *points: RecordPoint,
    total_ascent_m: float | None = None,
    total_descent_m: float | None = None,
    avg_grade_pct: float | None = None,
    total_work_j: float | None = None,
) -> Workout:
    return Workout(
        start_time=START,
        sport="cycling",
        total_ascent_m=total_ascent_m,
        total_descent_m=total_descent_m,
        avg_grade_pct=avg_grade_pct,
        total_work_j=total_work_j,
        records=list(points),
    )


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    distance_m: float | None = None,
    speed_ms: float | None = None,
    cadence: int | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        distance_m=distance_m,
        speed_ms=speed_ms,
        cadence=cadence,
    )


def test_compute_workout_metrics_averages_and_maxes_heart_rate() -> None:
    workout = _workout(_point(0, heart_rate=140), _point(1, heart_rate=150))

    metrics = compute_workout_metrics(workout)

    assert metrics.avg_heart_rate == 145.0
    assert metrics.max_heart_rate == 150


def test_compute_workout_metrics_averages_power() -> None:
    workout = _workout(_point(0, power=200), _point(1, power=220))

    metrics = compute_workout_metrics(workout)

    assert metrics.avg_power == 210.0


def test_compute_workout_metrics_takes_distance_as_the_last_cumulative_value() -> None:
    workout = _workout(_point(0, distance_m=0.0), _point(1, distance_m=8.5))

    metrics = compute_workout_metrics(workout)

    assert metrics.distance_m == 8.5


def test_compute_workout_metrics_is_none_for_a_field_never_recorded() -> None:
    """A ride with no power meter must not crash the analysis."""
    workout = _workout(_point(0, heart_rate=140), _point(1, heart_rate=150))

    metrics = compute_workout_metrics(workout)

    assert metrics.avg_power is None
    assert metrics.distance_m is None


def test_compute_workout_metrics_elapsed_time_spans_first_to_last_record() -> None:
    workout = _workout(_point(0), _point(30))

    metrics = compute_workout_metrics(workout)

    assert metrics.elapsed_time == timedelta(seconds=30)


def test_compute_workout_metrics_moving_time_excludes_a_pause() -> None:
    workout = _workout(_point(0), _point(1), _point(31))

    metrics = compute_workout_metrics(workout)

    assert metrics.elapsed_time == timedelta(seconds=31)
    assert metrics.moving_time == timedelta(seconds=1)


def test_compute_workout_metrics_moving_time_keeps_normal_one_second_gaps() -> None:
    """A gap right at the recording interval must not be flagged as a pause."""
    workout = _workout(_point(0), _point(1), _point(2))

    metrics = compute_workout_metrics(workout)

    assert metrics.moving_time == metrics.elapsed_time == timedelta(seconds=2)


def test_compute_workout_metrics_moving_time_never_exceeds_elapsed_time() -> None:
    workout = _workout(_point(0), _point(2), _point(4))

    metrics = compute_workout_metrics(workout)

    assert metrics.moving_time <= metrics.elapsed_time


def test_split_elapsed_and_moving_time_rejects_empty_records() -> None:
    with pytest.raises(deal.PreContractError):
        _split_elapsed_and_moving_time([])


def test_compute_workout_metrics_averages_and_maxes_speed_and_cadence() -> None:
    workout = _workout(
        _point(0, speed_ms=4.0, cadence=80), _point(1, speed_ms=6.0, cadence=90)
    )

    metrics = compute_workout_metrics(workout)

    assert metrics.avg_speed_ms == 5.0
    assert metrics.max_speed_ms == 6.0
    assert metrics.avg_cadence == 85.0
    assert metrics.max_cadence == 90


def test_compute_workout_metrics_is_none_for_speed_and_cadence_never_recorded() -> None:
    workout = _workout(_point(0, heart_rate=140), _point(1, heart_rate=150))

    metrics = compute_workout_metrics(workout)

    assert metrics.avg_speed_ms is None
    assert metrics.max_speed_ms is None
    assert metrics.avg_cadence is None
    assert metrics.max_cadence is None


def test_compute_workout_metrics_takes_elevation_from_the_device() -> None:
    workout = _workout(
        _point(0),
        total_ascent_m=520.0,
        total_descent_m=480.0,
        avg_grade_pct=1.2,
    )

    metrics = compute_workout_metrics(workout)

    assert metrics.elevation_gain_m == 520.0
    assert metrics.elevation_loss_m == 480.0
    assert metrics.avg_gradient_pct == 1.2


def test_compute_workout_metrics_elevation_is_none_without_a_device_value() -> None:
    workout = _workout(_point(0))

    metrics = compute_workout_metrics(workout)

    assert metrics.elevation_gain_m is None
    assert metrics.elevation_loss_m is None
    assert metrics.avg_gradient_pct is None


def test_compute_workout_metrics_prefers_device_total_work() -> None:
    workout = _workout(
        _point(0, power=100), _point(1, power=200), total_work_j=639616.0
    )

    metrics = compute_workout_metrics(workout)

    assert metrics.work_kj == 639.616


def test_compute_workout_metrics_falls_back_to_avg_power_for_work() -> None:
    workout = _workout(_point(0, power=100), _point(1, power=100))

    metrics = compute_workout_metrics(workout)

    assert metrics.work_kj == 100.0 * 1 / 1000


def test_compute_workout_metrics_vam_uses_elevation_gain_and_moving_time() -> None:
    """1 metre climbed in 1 second of moving_time is 3600 m/h."""
    workout = _workout(_point(0), _point(1), total_ascent_m=1.0)

    metrics = compute_workout_metrics(workout)

    assert metrics.vam == 3600.0


class TestVam:
    def test_none_without_elevation_gain(self) -> None:
        assert vam(None, timedelta(hours=1)) is None

    def test_none_for_zero_moving_time(self) -> None:
        assert vam(500.0, timedelta(0)) is None

    def test_scales_with_time(self) -> None:
        assert vam(1000.0, timedelta(hours=2)) == 500.0


class TestWorkKj:
    def test_prefers_device_total_work(self) -> None:
        assert _work_kj(639616.0, 135.0, timedelta(seconds=4958)) == 639.616

    def test_falls_back_to_avg_power_and_moving_time(self) -> None:
        assert _work_kj(None, 135.0, timedelta(seconds=1000)) == 135.0

    def test_none_without_any_power_figure(self) -> None:
        assert _work_kj(None, None, timedelta(seconds=1000)) is None
