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
