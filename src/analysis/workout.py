"""Summary metrics computed from a single workout."""

from datetime import timedelta
from itertools import pairwise
from typing import Final

import deal
from pydantic import BaseModel

from analysis.metrics import average
from models import RecordPoint, Workout

_PAUSE_GAP_THRESHOLD: Final = timedelta(seconds=2)
"""Records are 1s apart while a device is actively recording (seen in every
real workout file); a wider gap means recording stopped, whether from
auto-pause or lost signal. 2s sits safely between the two."""


class WorkoutMetrics(BaseModel):
    """Summary metrics computed from a single workout's records.

    Attributes:
        elapsed_time: Wall-clock time from the first to the last record,
            including any pauses.
        moving_time: elapsed_time with paused stretches subtracted.
        avg_heart_rate: Average heart rate in bpm, or None if no heart rate
            was recorded.
        max_heart_rate: Maximum heart rate in bpm, or None if no heart rate
            was recorded.
        avg_power: Average power in watts, or None if no power was recorded.
        distance_m: Total distance in metres, or None if no distance was
            recorded.
    """

    elapsed_time: timedelta
    moving_time: timedelta
    avg_heart_rate: float | None
    max_heart_rate: int | None
    avg_power: float | None
    distance_m: float | None


@deal.pre(lambda records: len(records) > 0)
@deal.ensure(lambda _: timedelta(0) <= _.result[1] <= _.result[0])
def _split_elapsed_and_moving_time(
    records: list[RecordPoint],
) -> tuple[timedelta, timedelta]:
    """Split a workout's records into elapsed time and moving time.

    Args:
        records: Time-ordered records of a workout; must not be empty.

    Returns:
        A pair ``(elapsed_time, moving_time)``: the wall-clock span from
        first to last record, and that same span with gaps wider than
        ``_PAUSE_GAP_THRESHOLD`` subtracted. ``moving_time`` always lies
        between zero and ``elapsed_time``.

    >>> from datetime import UTC, datetime
    >>> records = [
    ...     RecordPoint(timestamp=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)),
    ...     RecordPoint(timestamp=datetime(2026, 7, 16, 14, 0, 1, tzinfo=UTC)),
    ...     RecordPoint(timestamp=datetime(2026, 7, 16, 14, 0, 31, tzinfo=UTC)),
    ... ]
    >>> _split_elapsed_and_moving_time(records)
    (datetime.timedelta(seconds=31), datetime.timedelta(seconds=1))
    """
    elapsed_time = records[-1].timestamp - records[0].timestamp
    paused_time = sum(
        (
            later.timestamp - earlier.timestamp
            for earlier, later in pairwise(records)
            if later.timestamp - earlier.timestamp > _PAUSE_GAP_THRESHOLD
        ),
        start=timedelta(),
    )
    return elapsed_time, elapsed_time - paused_time


def compute_workout_metrics(workout: Workout) -> WorkoutMetrics:
    """Compute summary metrics for a single workout.

    A metric is None if the underlying quantity was never recorded, e.g.
    avg_power for a ride with no power meter — not an error, since that is
    an ordinary, expected state of the input data.

    Args:
        workout: The workout to summarise.

    Returns:
        The computed metrics.

    >>> from datetime import UTC, datetime
    >>> workout = Workout(
    ...     start_time=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC),
    ...             heart_rate=140,
    ...             distance_m=0.0,
    ...         ),
    ...         RecordPoint(
    ...             timestamp=datetime(2026, 7, 16, 14, 0, 1, tzinfo=UTC),
    ...             heart_rate=150,
    ...             distance_m=8.0,
    ...         ),
    ...     ],
    ... )
    >>> metrics = compute_workout_metrics(workout)
    >>> metrics.avg_heart_rate, metrics.max_heart_rate
    (145.0, 150)
    >>> metrics.avg_power is None
    True
    >>> metrics.distance_m
    8.0
    """
    elapsed_time, moving_time = _split_elapsed_and_moving_time(workout.records)

    heart_rates = [r.heart_rate for r in workout.records if r.heart_rate is not None]
    powers = [r.power for r in workout.records if r.power is not None]
    distances = [r.distance_m for r in workout.records if r.distance_m is not None]

    return WorkoutMetrics(
        elapsed_time=elapsed_time,
        moving_time=moving_time,
        avg_heart_rate=average(heart_rates) if heart_rates else None,
        max_heart_rate=max(heart_rates) if heart_rates else None,
        avg_power=average(powers) if powers else None,
        distance_m=max(distances) if distances else None,
    )
