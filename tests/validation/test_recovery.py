"""Tests for validation.recovery."""

from datetime import UTC, date, datetime

import pytest

from errors import DataValidationError
from models import RecoveryDay
from validation import validate_recovery_days

CYCLE_START = datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC)


def _day(
    day_of_month: int,
    resting_hr: int | None = None,
    hrv_ms: float | None = None,
    skin_temp_c: float | None = None,
) -> RecoveryDay:
    return RecoveryDay(
        date=date(2026, 7, day_of_month),
        cycle_start=CYCLE_START,
        resting_hr=resting_hr,
        hrv_ms=hrv_ms,
        skin_temp_c=skin_temp_c,
    )


def test_validate_recovery_days_keeps_plausible_values_untouched() -> None:
    days = [_day(23, resting_hr=57, hrv_ms=98.4, skin_temp_c=33.9)]

    cleaned, report = validate_recovery_days(days)

    assert cleaned[0].hrv_ms == 98.4
    assert cleaned[0].skin_temp_c == 33.9
    assert report.is_clean


def test_validate_recovery_days_discards_implausible_hrv() -> None:
    days = [_day(23, resting_hr=57, hrv_ms=980.0)]

    cleaned, report = validate_recovery_days(days)

    assert cleaned[0].hrv_ms is None
    assert cleaned[0].resting_hr == 57
    assert report.discarded == {"hrv_ms": 1}


def test_validate_recovery_days_discards_strap_off_skin_temperature() -> None:
    days = [_day(23, skin_temp_c=8.0)]

    cleaned, report = validate_recovery_days(days)

    assert cleaned[0].skin_temp_c is None
    assert report.discarded == {"skin_temp_c": 1}


def test_validate_recovery_days_keeps_missing_values_missing() -> None:
    days = [_day(23)]

    cleaned, report = validate_recovery_days(days)

    assert cleaned[0].hrv_ms is None
    assert report.is_clean


def test_validate_recovery_days_rejects_duplicate_day() -> None:
    days = [_day(23, resting_hr=57), _day(23, resting_hr=58)]

    with pytest.raises(DataValidationError):
        validate_recovery_days(days)


def test_validate_recovery_days_accepts_empty_input() -> None:
    cleaned, report = validate_recovery_days([])

    assert cleaned == []
    assert report.is_clean


def test_validate_recovery_days_does_not_mutate_its_input() -> None:
    days = [_day(23, hrv_ms=980.0)]

    validate_recovery_days(days)

    assert days[0].hrv_ms == 980.0
