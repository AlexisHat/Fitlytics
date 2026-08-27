"""What the athlete actually rode recently, as the recommendation's input."""

from datetime import date
from typing import Final

import deal
from pydantic import BaseModel

from analysis.ftp import effective_ftp
from intervals import (
    IntervalType,
    build_interval_blocks,
    classify_session,
    find_candidates,
    has_strictly_increasing_timestamps,
    mark_standstill,
    resample_to_1hz,
    smooth_power,
)
from models import Workout, WorkoutCategory

WINDOW_SIZE: Final = 5
"""How many past sessions the recommendation looks at. Five covers roughly
a fortnight of riding for an athlete training three to four times a week —
long enough that one unusual ride does not dominate, short enough that the
window still describes the current block rather than last month's."""


class SessionSummary(BaseModel):
    """One past session, reduced to what the recommendation needs.

    Attributes:
        date: Local date the session was recorded on.
        category: What the athlete tagged the session as, or None if they
            left it untagged.
        interval_type: The type detected within the session, or None if it
            was not an interval session, carried no FTP to scale against,
            or held no detectable blocks.
    """

    date: date
    category: WorkoutCategory | None
    interval_type: IntervalType | None


def session_interval_type(
    workout: Workout, profile_ftp: int | None
) -> IntervalType | None:
    """Detect which kind of intervals a past session actually contained.

    Runs only on a session the athlete tagged as intervals, for the same
    reason the analysis button is gated that way: every ride has some
    hardest stretch, and on an endurance ride that is a climb rather than
    a deliberate effort. Typing those would fill the history with
    intervals that were never ridden.

    Args:
        workout: The past session.
        profile_ftp: The athlete's current FTP, used only for a workout
            that carries none of its own.

    Returns:
        The session's interval type, or None if it was not tagged as an
        interval session, has no usable FTP, has unusable timestamps, or
        contained no detectable blocks.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> from models import RecordPoint
    >>> ride = Workout(
    ...     start_time=start,
    ...     sport="cycling",
    ...     records=[RecordPoint(timestamp=start, power=200)],
    ... )
    >>> session_interval_type(ride, 250) is None
    True
    """
    if workout.category is not WorkoutCategory.INTERVALLE:
        return None

    ftp_watts = effective_ftp(workout, profile_ftp)
    if ftp_watts is None or not has_strictly_increasing_timestamps(workout.records):
        return None

    series = mark_standstill(smooth_power(resample_to_1hz(workout.records)))
    candidates = find_candidates(series)
    if not candidates:
        return None
    return classify_session(build_interval_blocks(series, candidates, ftp_watts))


@deal.pre(
    lambda workouts, today, profile_ftp=None, window_size=WINDOW_SIZE: window_size > 0
)
@deal.ensure(lambda _: len(_.result) <= _.window_size)
def recent_sessions(
    workouts: list[Workout],
    today: date,
    profile_ftp: int | None = None,
    window_size: int = WINDOW_SIZE,
) -> list[SessionSummary]:
    """Summarise the most recent sessions up to and including today.

    Sessions in the future are ignored rather than treated as history: a
    workout dated after today can only come from a device with a wrong
    clock, and letting it into the window would describe training that has
    not happened.

    Args:
        workouts: Every stored workout, in any order.
        today: The day the recommendation is being made for.
        profile_ftp: The athlete's current FTP, used only for workouts
            that carry none of their own.
        window_size: How many sessions to look back over; must be positive.

    Returns:
        Up to ``window_size`` summaries, oldest first, matching the order
        workouts are held in elsewhere.

    Raises:
        deal.PreContractError: If ``window_size`` is not positive.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint
    >>> def ride(day: int) -> Workout:
    ...     start = datetime(2026, 7, day, 9, 0, tzinfo=UTC)
    ...     return Workout(
    ...         start_time=start,
    ...         sport="cycling",
    ...         category=WorkoutCategory.GRUNDLAGE,
    ...         records=[RecordPoint(timestamp=start, power=150)],
    ...     )
    >>> sessions = recent_sessions(
    ...     [ride(1), ride(2), ride(3)], date(2026, 7, 3), window_size=2
    ... )
    >>> [session.date.day for session in sessions]
    [2, 3]
    """
    past = sorted(
        (workout for workout in workouts if workout.start_time.date() <= today),
        key=lambda workout: workout.start_time,
    )
    return [
        SessionSummary(
            date=workout.start_time.date(),
            category=workout.category,
            interval_type=session_interval_type(workout, profile_ftp),
        )
        for workout in past[-window_size:]
    ]
