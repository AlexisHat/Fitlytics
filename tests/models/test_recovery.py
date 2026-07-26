"""Tests for models.recovery."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from models import RecoveryDay

CYCLE_START = datetime(2026, 7, 23, 1, 43, 25, tzinfo=UTC)


def test_recovery_day_accepts_float_hrv() -> None:
    day = RecoveryDay(
        date=date(2026, 7, 23),
        cycle_start=CYCLE_START,
        recovery_score=73,
        resting_hr=57,
        hrv_ms=98.4,
    )

    assert day.hrv_ms == 98.4


def test_recovery_day_accepts_the_bounds_of_a_percentage() -> None:
    day = RecoveryDay(
        date=date(2026, 7, 23),
        cycle_start=CYCLE_START,
        recovery_score=0,
        blood_oxygen=100.0,
    )

    assert day.recovery_score == 0
    assert day.blood_oxygen == 100.0


@pytest.mark.parametrize("score", [-1, 101])
def test_recovery_day_rejects_impossible_recovery_score(score: int) -> None:
    with pytest.raises(PydanticValidationError):
        RecoveryDay(
            date=date(2026, 7, 23), cycle_start=CYCLE_START, recovery_score=score
        )


def test_recovery_day_rejects_impossible_blood_oxygen() -> None:
    with pytest.raises(PydanticValidationError):
        RecoveryDay(date=date(2026, 7, 23), cycle_start=CYCLE_START, blood_oxygen=120.0)


def test_recovery_day_rejects_non_positive_resting_hr() -> None:
    with pytest.raises(PydanticValidationError):
        RecoveryDay(date=date(2026, 7, 23), cycle_start=CYCLE_START, resting_hr=0)
