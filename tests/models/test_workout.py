"""Tests for models.workout."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from models import RecordPoint, Workout


def test_workout_construction_succeeds_with_valid_data() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        sub_sport="generic",
        ftp_watts=210,
        records=[
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), heart_rate=120
            ),
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 40, tzinfo=UTC), heart_rate=121
            ),
        ],
    )

    assert workout.sport == "cycling"
    assert workout.ftp_watts == 210
    assert len(workout.records) == 2


def test_workout_requires_at_least_one_record() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="cycling",
            records=[],
        )


def test_workout_rejects_empty_sport() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="",
            records=[
                RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))
            ],
        )


def test_record_point_accepts_zero_power_and_cadence() -> None:
    """Coasting downhill is a genuine reading, not a missing value."""
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), power=0, cadence=0
    )

    assert point.power == 0
    assert point.cadence == 0


@pytest.mark.parametrize("field", ["heart_rate", "power", "cadence"])
def test_record_point_rejects_negative_measurements(field: str) -> None:
    with pytest.raises(PydanticValidationError):
        RecordPoint(
            timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), **{field: -1}
        )


def test_record_point_allows_negative_altitude() -> None:
    """Below sea level is a real place, not a sensor error."""
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), altitude_m=-4.2
    )

    assert point.altitude_m == -4.2


def test_workout_allows_negative_avg_grade() -> None:
    """A net-downhill course is a real profile, not a sensor error."""
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        avg_grade_pct=-1.5,
        records=[RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))],
    )

    assert workout.avg_grade_pct == -1.5


def test_workout_rejects_negative_total_ascent() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="cycling",
            total_ascent_m=-1.0,
            records=[
                RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))
            ],
        )
