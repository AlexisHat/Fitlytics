"""Tests for models.recovery."""

from datetime import UTC, date, datetime

from models import RecoveryDay


def test_recovery_day_accepts_float_hrv() -> None:
    day = RecoveryDay(
        date=date(2026, 7, 23),
        cycle_start=datetime(2026, 7, 23, 1, 43, 25, tzinfo=UTC),
        recovery_score=73,
        resting_hr=57,
        hrv_ms=98.4,
    )

    assert day.hrv_ms == 98.4
