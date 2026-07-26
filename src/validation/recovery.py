"""Validate imported recovery days and discard implausible measurements."""

from collections import Counter
from datetime import date

import deal

from errors import DataValidationError
from models import RecoveryDay
from validation.ranges import (
    HRV_MS,
    RESPIRATORY_RATE,
    RESTING_HR_BPM,
    SKIN_TEMP_C,
    Bounds,
    keep_within,
)
from validation.report import ValidationReport


def _clean_recovery_day(day: RecoveryDay) -> tuple[RecoveryDay, list[str]]:
    """Discard the implausible measurements of a single recovery day.

    Args:
        day: The recovery day to check.

    Returns:
        The day with implausible values replaced by None, and the names of
        the fields that were discarded.

    >>> from datetime import UTC, date, datetime
    >>> day = RecoveryDay(
    ...     date=date(2026, 7, 23),
    ...     cycle_start=datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC),
    ...     resting_hr=57,
    ...     hrv_ms=980.0,
    ... )
    >>> cleaned, discarded = _clean_recovery_day(day)
    >>> cleaned.resting_hr, cleaned.hrv_ms is None
    (57, True)
    >>> discarded
    ['hrv_ms']
    """
    checks: tuple[tuple[str, float | None, Bounds], ...] = (
        ("resting_hr", day.resting_hr, RESTING_HR_BPM),
        ("hrv_ms", day.hrv_ms, HRV_MS),
        ("skin_temp_c", day.skin_temp_c, SKIN_TEMP_C),
        ("respiratory_rate", day.respiratory_rate, RESPIRATORY_RATE),
    )

    update: dict[str, float | None] = {}
    discarded: list[str] = []
    for name, value, (low, high) in checks:
        kept = keep_within(low, high, value)
        update[name] = kept
        if kept is None and value is not None:
            discarded.append(name)

    return day.model_copy(update=update), discarded


@deal.raises(DataValidationError)
@deal.ensure(lambda _: len(_.result[0]) == len(_.days))
def validate_recovery_days(
    days: list[RecoveryDay],
) -> tuple[list[RecoveryDay], ValidationReport]:
    """Discard implausible measurements from imported recovery days.

    Two entries reporting on the same day are rejected rather than merged.
    Once cycles are mapped to the day they report on, a duplicate can no
    longer come from a late bedtime; it means the export was concatenated
    or edited, and silently picking one of the two would fake a day of
    recovery that was never measured.

    Args:
        days: The imported recovery days to validate.

    Returns:
        The days with implausible values replaced by None, and a report of
        what was discarded.

    Raises:
        DataValidationError: If two entries report on the same day.

    >>> from datetime import UTC, date, datetime
    >>> days = [
    ...     RecoveryDay(
    ...         date=date(2026, 7, 23),
    ...         cycle_start=datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC),
    ...         resting_hr=57,
    ...         skin_temp_c=99.0,
    ...     )
    ... ]
    >>> cleaned, report = validate_recovery_days(days)
    >>> cleaned[0].skin_temp_c is None
    True
    >>> report.summary()
    'discarded implausible values: 1 skin_temp_c value'
    """
    seen: set[date] = set()
    for day in days:
        if day.date in seen:
            raise DataValidationError(f"duplicate recovery entry for {day.date}")
        seen.add(day.date)

    discarded: Counter[str] = Counter()
    cleaned: list[RecoveryDay] = []
    for day in days:
        cleaned_day, dropped_fields = _clean_recovery_day(day)
        cleaned.append(cleaned_day)
        discarded.update(dropped_fields)

    return cleaned, ValidationReport(discarded=dict(discarded))
