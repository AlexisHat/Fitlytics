"""Validate an imported workout and discard implausible measurements."""

from collections import Counter
from itertools import pairwise

import deal

from errors import DataValidationError
from models import RecordPoint, Workout
from validation.ranges import (
    CADENCE_RPM,
    HEART_RATE_BPM,
    POWER_W,
    SPEED_MS,
    Bounds,
    keep_within,
)
from validation.report import ValidationReport


def _clean_record(point: RecordPoint) -> tuple[RecordPoint, list[str]]:
    """Discard the implausible measurements of a single record point.

    Args:
        point: The record point to check.

    Returns:
        The point with implausible values replaced by None, and the names
        of the fields that were discarded.

    >>> from datetime import UTC, datetime
    >>> point = RecordPoint(
    ...     timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
    ...     heart_rate=250,
    ...     power=180,
    ... )
    >>> cleaned, discarded = _clean_record(point)
    >>> cleaned.heart_rate is None, cleaned.power
    (True, 180)
    >>> discarded
    ['heart_rate']
    """
    checks: tuple[tuple[str, float | None, Bounds], ...] = (
        ("heart_rate", point.heart_rate, HEART_RATE_BPM),
        ("power", point.power, POWER_W),
        ("cadence", point.cadence, CADENCE_RPM),
        ("speed_ms", point.speed_ms, SPEED_MS),
    )

    update: dict[str, float | None] = {}
    discarded: list[str] = []
    for name, value, (low, high) in checks:
        kept = keep_within(low, high, value)
        update[name] = kept
        if kept is None and value is not None:
            discarded.append(name)

    return point.model_copy(update=update), discarded


@deal.raises(DataValidationError)
@deal.ensure(lambda _: len(_.result[0].records) == len(_.workout.records))
def validate_workout(workout: Workout) -> tuple[Workout, ValidationReport]:
    """Discard implausible measurements from an imported workout.

    Only individual values are dropped, never whole records: one dropout of
    the chest strap must not cost a two-hour ride its timeline, and keeping
    the record preserves the spacing every later time series relies on.

    Records out of chronological order are a different matter — no analysis
    downstream can repair that — so such a workout is rejected outright.

    Args:
        workout: The imported workout to validate.

    Returns:
        The workout with implausible values replaced by None, and a report
        of what was discarded.

    Raises:
        DataValidationError: If the records are not in chronological order.

    >>> from datetime import UTC, datetime
    >>> workout = Workout(
    ...     start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
    ...             heart_rate=142,
    ...         ),
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 11, 40, tzinfo=UTC),
    ...             heart_rate=250,
    ...         ),
    ...     ],
    ... )
    >>> cleaned, report = validate_workout(workout)
    >>> [point.heart_rate for point in cleaned.records]
    [142, None]
    >>> report.summary()
    'discarded implausible values: 1 heart_rate value'
    """
    for earlier, later in pairwise(workout.records):
        if earlier.timestamp > later.timestamp:
            raise DataValidationError("workout records are not in chronological order")

    discarded: Counter[str] = Counter()
    records: list[RecordPoint] = []
    for point in workout.records:
        cleaned_point, dropped_fields = _clean_record(point)
        records.append(cleaned_point)
        discarded.update(dropped_fields)

    cleaned = workout.model_copy(update={"records": records})
    return cleaned, ValidationReport(discarded=dict(discarded))
