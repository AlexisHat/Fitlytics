"""Tests for analysis.workout."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from analysis import compute_workout_metrics
from analysis.workout import _split_elapsed_and_moving_time
from models import RecordPoint, Workout

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(*points: RecordPoint) -> Workout:
    return Workout(start_time=START, sport="cycling", records=list(points))


def _point(
    offset_s: int,
    heart_rate: int | None = None,
    power: int | None = None,
    distance_m: float | None = None,
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        heart_rate=heart_rate,
        power=power,
        distance_m=distance_m,
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
