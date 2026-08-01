"""Tests for validation.workout."""

from datetime import UTC, datetime, timedelta

import pytest

from errors import DataValidationError
from models import RecordPoint, Workout
from validation import validate_workout

START = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)


def _workout(*points: RecordPoint) -> Workout:
    return Workout(start_time=START, sport="cycling", records=list(points))


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


def test_validate_workout_keeps_plausible_values_untouched() -> None:
    workout = _workout(_point(0, heart_rate=142, power=210, cadence=88))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].heart_rate == 142
    assert cleaned.records[0].power == 210
    assert report.is_clean


def test_validate_workout_keeps_zero_power_and_cadence() -> None:
    """Coasting is a genuine reading, not a dropout."""
    workout = _workout(_point(0, power=0, cadence=0, speed_ms=0.0))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].power == 0
    assert cleaned.records[0].cadence == 0
    assert report.is_clean


def test_validate_workout_discards_implausible_heart_rate() -> None:
    workout = _workout(_point(0, heart_rate=250, power=210))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].heart_rate is None
    assert cleaned.records[0].power == 210
    assert report.discarded == {"heart_rate": 1}


def test_validate_workout_keeps_negative_grade() -> None:
    """A descent is a plausible gradient, not a dropout."""
    workout = _workout(_point(0, grade_pct=-3.82))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].grade_pct == -3.82
    assert report.is_clean


def test_validate_workout_discards_implausible_grade() -> None:
    workout = _workout(_point(0, grade_pct=55.0))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].grade_pct is None
    assert report.discarded == {"grade_pct": 1}


def test_validate_workout_discards_dropout_heart_rate() -> None:
    """A strap that lost contact reports 0, which is not a heart rate."""
    workout = _workout(_point(0, heart_rate=0))

    cleaned, report = validate_workout(workout)

    assert cleaned.records[0].heart_rate is None
    assert report.discarded == {"heart_rate": 1}


def test_validate_workout_keeps_every_record() -> None:
    workout = _workout(_point(0, heart_rate=250), _point(1, heart_rate=142))

    cleaned, _ = validate_workout(workout)

    assert len(cleaned.records) == 2
    assert [point.timestamp for point in cleaned.records] == [
        point.timestamp for point in workout.records
    ]


def test_validate_workout_counts_discards_across_records_and_fields() -> None:
    workout = _workout(
        _point(0, heart_rate=250, power=9000),
        _point(1, heart_rate=300),
        _point(2, heart_rate=142),
    )

    _, report = validate_workout(workout)

    assert report.discarded == {"heart_rate": 2, "power": 1}
    assert report.total == 3


def test_validate_workout_does_not_mutate_its_input() -> None:
    workout = _workout(_point(0, heart_rate=250))

    validate_workout(workout)

    assert workout.records[0].heart_rate == 250


def test_validate_workout_rejects_records_out_of_order() -> None:
    workout = _workout(_point(10, heart_rate=142), _point(0, heart_rate=143))

    with pytest.raises(DataValidationError):
        validate_workout(workout)


def test_validate_workout_accepts_equal_timestamps() -> None:
    workout = _workout(_point(0, heart_rate=142), _point(0, heart_rate=143))

    cleaned, _ = validate_workout(workout)

    assert len(cleaned.records) == 2
