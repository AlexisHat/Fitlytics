"""Per-day aggregation of workouts for a Github-style calendar view."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from itertools import pairwise

import deal
from pydantic import BaseModel, NonNegativeFloat

from analysis.load import training_load
from models import Workout


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


@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
@deal.ensure(
    lambda _: (
        _.result == ()
        or all(b.date - a.date == timedelta(days=1) for a, b in pairwise(_.result))
    )
)
def build_calendar(
    workouts: Sequence[Workout],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> tuple[CalendarDay, ...]:
    """Aggregate workouts into one calendar day per day in their date range.

    A day with no workout (never mind whether the athlete recovered that
    day — recovery isn't part of this view) is a real, expected rest day,
    not missing data, so it appears with ``training_load=0.0`` rather than
    being left out of the range.

    Args:
        workouts: The workouts to aggregate; may be empty.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        One CalendarDay per calendar day from the earliest to the latest
        workout's UTC start date, inclusive and without gaps. Empty if
        ``workouts`` is empty.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint
    >>> day_one = Workout(
    ...     start_time=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...             heart_rate=140,
    ...         )
    ...     ],
    ... )
    >>> day_three = day_one.model_copy(
    ...     update={"start_time": datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC)}
    ... )
    >>> calendar = build_calendar(
    ...     [day_one, day_three], ftp_watts=None, hr_rest=50, hr_max=190
    ... )
    >>> [(day.date.isoformat(), len(day.workouts)) for day in calendar]
    [('2026-07-16', 1), ('2026-07-17', 0), ('2026-07-18', 1)]
    """
    if not workouts:
        return ()

    by_day: dict[date, list[Workout]] = defaultdict(list)
    for workout in workouts:
        by_day[workout.start_time.date()].append(workout)

    first_day = min(by_day)
    last_day = max(by_day)

    days: list[CalendarDay] = []
    current = first_day
    while current <= last_day:
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
        current += timedelta(days=1)
    return tuple(days)
