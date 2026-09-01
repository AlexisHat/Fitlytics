"""Per-day aggregation of workouts for a Github-style calendar view."""

from calendar import monthrange
from collections import defaultdict
from collections.abc import Sequence
from datetime import MAXYEAR, MINYEAR, date
from typing import Final

import deal
from pydantic import BaseModel, NonNegativeFloat

from analysis.load import training_load
from models import Workout

_REFERENCE_TSS: Final = 250
"""TSS at which a day's calendar colour reaches 100%. Picked by the athlete
to subjectively match how their own sessions feel, not a published zone
boundary. Fixed rather than relative to the days shown, so a given workout's
colour no longer depends on what else happened in its calendar month or view
— see docs/entscheidungen.md. TRIMP days (no power meter or FTP) are scaled
on the same fixed number, which is not on a comparable scale; accepted for
this single-athlete, power-meter-first app rather than building out a second
reference for the rarely-used fallback."""


class CalendarDay(BaseModel):
    """One calendar day's aggregated training load.

    Attributes:
        date: The calendar day, from a workout's UTC start date (FIT files
            carry no local timezone to convert to).
        training_load: Summed training load of the day's workouts; 0.0 on
            a rest day, and also if a day's workouts had no computable load
            (missing power meter and heart-rate profile alike).
        workouts: The day's workouts, in recording order; empty on a rest
            day. Kept here rather than just a count so a UI can jump
            straight from a clicked day to its workout without re-filtering
            the full workout list itself.
    """

    date: date
    training_load: NonNegativeFloat
    workouts: tuple[Workout, ...]


@deal.pre(lambda _: MINYEAR <= _.year <= MAXYEAR)
@deal.pre(lambda _: 1 <= _.month <= 12)
@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
@deal.ensure(lambda _: len(_.result) == monthrange(_.year, _.month)[1])
def build_calendar(
    workouts: Sequence[Workout],
    year: int,
    month: int,
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> tuple[CalendarDay, ...]:
    """Aggregate one calendar month's workouts into one CalendarDay per day.

    A day with no workout (never mind whether the athlete recovered that
    day — recovery isn't part of this view) is a real, expected rest day,
    not missing data, so it appears with ``training_load=0.0`` rather than
    being left out of the month.

    Args:
        workouts: The workouts to aggregate; those outside ``year``/``month``
            are ignored.
        year: The calendar year to build; must be a year ``date`` can
            represent (1-9999).
        month: The calendar month to build, 1-12.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        One CalendarDay per day of ``year``-``month``, from the 1st to the
        last, inclusive, whether or not it has a workout.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint
    >>> workout = Workout(
    ...     start_time=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...             heart_rate=140,
    ...         )
    ...     ],
    ... )
    >>> calendar = build_calendar(
    ...     [workout], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    ... )
    >>> len(calendar)
    31
    >>> calendar[15].date.isoformat(), len(calendar[15].workouts)
    ('2026-07-16', 1)
    """
    by_day: dict[date, list[Workout]] = defaultdict(list)
    for workout in workouts:
        workout_date = workout.start_time.date()
        if workout_date.year == year and workout_date.month == month:
            by_day[workout_date].append(workout)

    _, days_in_month = monthrange(year, month)

    days: list[CalendarDay] = []
    for day_of_month in range(1, days_in_month + 1):
        current = date(year, month, day_of_month)
        day_workouts = tuple(by_day.get(current, ()))
        loads = (
            training_load(workout, ftp_watts, hr_rest, hr_max)
            for workout in day_workouts
        )
        total_load = sum(load for load in loads if load is not None)
        days.append(
            CalendarDay(
                date=current,
                training_load=max(0.0, total_load),
                workouts=day_workouts,
            )
        )
    return tuple(days)


@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
@deal.ensure(lambda _: all(load > 0 for load in _.result.values()))
def daily_training_load(
    workouts: Sequence[Workout],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> dict[date, float]:
    """Sum each day's training load, over any span rather than one month.

    Unlike :func:`build_calendar`, rest days are left out entirely: a caller
    drawing markers onto a chart wants the days that carry a load, not one
    entry per day of an arbitrarily long span. Days whose workouts have no
    computable load (no power meter and no heart-rate profile) drop out for
    the same reason — nothing to draw.

    Args:
        workouts: The workouts to aggregate, in any order.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The summed load per calendar day, keyed by the day's UTC date and
        holding only days with a load above zero.

    Raises:
        deal.PreContractError: If the profile values are out of range.

    Two rides on the same day are summed into one entry, and the rest day
    between them never appears:

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> def ride(day: int, hour: int) -> Workout:
    ...     start = datetime(2026, 7, day, hour, 0, 0, tzinfo=UTC)
    ...     return Workout(
    ...         start_time=start,
    ...         sport="cycling",
    ...         records=[
    ...             RecordPoint(timestamp=start + timedelta(seconds=i), power=200)
    ...             for i in range(30)
    ...         ],
    ...     )
    >>> loads = daily_training_load(
    ...     [ride(16, 8), ride(16, 17), ride(18, 8)], 210, hr_rest=50, hr_max=190
    ... )
    >>> [day.isoformat() for day in loads]
    ['2026-07-16', '2026-07-18']
    >>> loads[date(2026, 7, 16)] == 2 * loads[date(2026, 7, 18)]
    True
    """
    totals: dict[date, float] = defaultdict(float)
    for workout in workouts:
        load = training_load(workout, ftp_watts, hr_rest, hr_max)
        if load is not None and load > 0:
            totals[workout.start_time.date()] += load
    return dict(sorted(totals.items()))


@deal.pre(lambda _: _.value >= 0)
@deal.post(lambda result: 0 <= result <= 100)
def training_load_intensity_pct(value: float) -> int:
    """Scale a day's training load to a fixed 0-100% intensity.

    ``_REFERENCE_TSS`` is 100%, a rest day is 0%, and every load in between
    is placed linearly; a load above the reference is capped at 100%. Fixed
    rather than relative to any calendar range, so a workout's colour is the
    same no matter which month it is viewed in.

    Args:
        value: The training load of the day being scaled; must be
            non-negative.

    Returns:
        0 for a rest day (``value == 0``); otherwise how hard ``value`` is
        relative to ``_REFERENCE_TSS``, as a percentage from 1 to 100.

    >>> training_load_intensity_pct(0.0)
    0
    >>> training_load_intensity_pct(125.0)
    50
    >>> training_load_intensity_pct(400.0)
    100
    """
    if value <= 0:
        return 0

    return round(min(value, _REFERENCE_TSS) / _REFERENCE_TSS * 100)
