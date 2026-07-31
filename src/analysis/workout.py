"""Summary metrics computed from a single workout."""

from datetime import timedelta
from itertools import pairwise

import deal
from pydantic import BaseModel

from analysis.constants import PAUSE_GAP_THRESHOLD
from analysis.metrics import average
from models import RecordPoint, Workout


class WorkoutMetrics(BaseModel):
    """Summary metrics computed from a single workout's records.

    elevation_gain_m, elevation_loss_m and avg_gradient_pct are taken from
    the device's own session fields rather than recomputed from raw
    altitude samples: a device's barometric smoothing is a mature algorithm
    that a naive sum of altitude deltas would not reproduce (noise in the
    raw signal would be counted as climbing). work_kj prefers the same
    device figure for the same reason, with a fallback for devices that
    don't report it.

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
        avg_speed_ms: Average speed in metres per second, or None if no
            speed was recorded.
        max_speed_ms: Maximum speed in metres per second, or None if no
            speed was recorded.
        avg_cadence: Average cadence in rpm, or None if no cadence was
            recorded.
        max_cadence: Maximum cadence in rpm, or None if no cadence was
            recorded.
        elevation_gain_m: Total climbed elevation in metres, as reported by
            the device, or None if unavailable.
        elevation_loss_m: Total descended elevation in metres, as reported
            by the device, or None if unavailable.
        avg_gradient_pct: Average gradient over the session, as reported by
            the device, or None if unavailable.
        vam: Climbing rate in metres per hour, simplified to the whole
            workout's elevation_gain_m over moving_time, or None if either
            is unavailable.
        work_kj: Total mechanical work in kilojoules, or None if neither
            the device figure nor avg_power is available.
    """

    elapsed_time: timedelta
    moving_time: timedelta
    avg_heart_rate: float | None
    max_heart_rate: int | None
    avg_power: float | None
    distance_m: float | None
    avg_speed_ms: float | None
    max_speed_ms: float | None
    avg_cadence: float | None
    max_cadence: int | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    avg_gradient_pct: float | None
    vam: float | None
    work_kj: float | None


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
        ``PAUSE_GAP_THRESHOLD`` subtracted. ``moving_time`` always lies
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
            if later.timestamp - earlier.timestamp > PAUSE_GAP_THRESHOLD
        ),
        start=timedelta(),
    )
    return elapsed_time, elapsed_time - paused_time


def vam(elevation_gain_m: float | None, moving_time: timedelta) -> float | None:
    """Compute VAM: vertical ascent rate in metres climbed per hour.

    Simplified to the whole workout rather than a single climb, which is
    what VAM traditionally refers to — a ride that includes flat sections
    will show a lower VAM than the climb within it actually had. A true
    per-climb VAM belongs to interval/climb detection, not here.

    Args:
        elevation_gain_m: The workout's total climbed elevation, or None.
        moving_time: The workout's moving time.

    Returns:
        elevation_gain_m per hour of moving_time, or None if
        elevation_gain_m is missing or moving_time is zero.

    >>> from datetime import timedelta
    >>> vam(500.0, timedelta(hours=2))
    250.0
    >>> vam(None, timedelta(hours=1)) is None
    True
    """
    if elevation_gain_m is None or moving_time <= timedelta(0):
        return None
    hours = moving_time.total_seconds() / 3600
    return elevation_gain_m / hours


def _work_kj(
    total_work_j: float | None, avg_power: float | None, moving_time: timedelta
) -> float | None:
    """Compute total mechanical work in kilojoules.

    Prefers the device's own total_work_j — the true integral of power over
    time — over avg_power x moving_time, which assumes a constant power
    output for the whole moving time and so only approximates the same
    quantity.

    Args:
        total_work_j: The device-reported total work in joules, or None.
        avg_power: The workout's average power in watts, or None.
        moving_time: The workout's moving time.

    Returns:
        The work in kilojoules, or None if neither total_work_j nor
        avg_power is available.

    >>> from datetime import timedelta
    >>> _work_kj(639616.0, None, timedelta(seconds=4958))
    639.616
    >>> _work_kj(None, 135.0, timedelta(seconds=4958))
    669.33
    >>> _work_kj(None, None, timedelta(seconds=4958)) is None
    True
    """
    if total_work_j is not None:
        return total_work_j / 1000
    if avg_power is not None:
        return avg_power * moving_time.total_seconds() / 1000
    return None


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
    speeds = [r.speed_ms for r in workout.records if r.speed_ms is not None]
    cadences = [r.cadence for r in workout.records if r.cadence is not None]

    avg_power = average(powers) if powers else None

    return WorkoutMetrics(
        elapsed_time=elapsed_time,
        moving_time=moving_time,
        avg_heart_rate=average(heart_rates) if heart_rates else None,
        max_heart_rate=max(heart_rates) if heart_rates else None,
        avg_power=avg_power,
        distance_m=max(distances) if distances else None,
        avg_speed_ms=average(speeds) if speeds else None,
        max_speed_ms=max(speeds) if speeds else None,
        avg_cadence=average(cadences) if cadences else None,
        max_cadence=max(cadences) if cadences else None,
        elevation_gain_m=workout.total_ascent_m,
        elevation_loss_m=workout.total_descent_m,
        avg_gradient_pct=workout.avg_grade_pct,
        vam=vam(workout.total_ascent_m, moving_time),
        work_kj=_work_kj(workout.total_work_j, avg_power, moving_time),
    )
