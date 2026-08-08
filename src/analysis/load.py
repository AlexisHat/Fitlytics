"""Intensity and training-load metrics for a single workout.

Normalized Power (NP), Intensity Factor (IF), TSS and the Variability Index
are Coggan's power-based load metrics. They build on each other: NP is the
foundation, IF relates it to the athlete's FTP, and TSS combines both with
the session's duration. FTP is never hard-coded — every function takes it
(and TRIMP's hr_rest/hr_max) as an explicit parameter, defaulting to None,
so a missing athlete profile yields None results instead of failing.

Unlike Normalized Power, TRIMP (Banister's Training Impulse) is heart-rate
based and does not appear as a device-computed session field at all, so it
is entirely our own computation.
"""

import math
from datetime import timedelta
from itertools import pairwise

import deal

from analysis.constants import PAUSE_GAP_THRESHOLD
from analysis.workout import compute_workout_metrics
from models import RecordPoint, Workout

_NP_WINDOW = 30
"""Rolling-average window in samples for Normalized Power, per Coggan's
definition (30 seconds at the ~1 Hz sampling rate our workouts use)."""

_TRIMP_MALE_CONSTANTS = (0.64, 1.92)
"""Banister's exponential weighting constants for male athletes; the
commonly published female constants (0.86, 1.67) differ and are not
supported here, since the course data is a single athlete's own training."""


def normalized_power(records: list[RecordPoint]) -> float | None:
    """Compute Normalized Power.

    The 30s-rolling-average power, 4th-power weighted to reward surges over
    a flat effort of the same average.

    Args:
        records: Time-ordered records of a workout.

    Returns:
        Normalized power in watts, or None if fewer than 30 power samples
        are available (too short for the rolling window this metric is
        defined over).

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start + timedelta(seconds=i), power=200)
    ...     for i in range(30)
    ... ]
    >>> normalized_power(records)
    200.0
    >>> normalized_power(records[:29]) is None
    True
    """
    powers = [r.power for r in records if r.power is not None]
    if len(powers) < _NP_WINDOW:
        return None

    rolling_averages = [
        sum(powers[start : start + _NP_WINDOW]) / _NP_WINDOW
        for start in range(len(powers) - _NP_WINDOW + 1)
    ]
    fourth_power_mean = sum(p**4 for p in rolling_averages) / len(rolling_averages)
    return math.pow(fourth_power_mean, 0.25)


@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
def intensity_factor(
    normalized_power: float | None, ftp_watts: int | None
) -> float | None:
    """Compute Intensity Factor: Normalized Power relative to FTP.

    Args:
        normalized_power: The workout's normalized power in watts, or None.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.

    Returns:
        normalized_power / ftp_watts, or None if either input is missing.

    >>> round(intensity_factor(182.0, 210), 3)
    0.867
    >>> intensity_factor(None, 210) is None
    True
    """
    if normalized_power is None or ftp_watts is None:
        return None
    return normalized_power / ftp_watts


@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
def training_stress_score(
    normalized_power: float | None,
    intensity_factor: float | None,
    moving_time: timedelta,
    ftp_watts: int | None,
) -> float | None:
    """Compute Training Stress Score (Coggan's formula).

    TSS = (moving_time_seconds x NP x IF) / (FTP x 3600) x 100 — a 1-hour
    effort exactly at FTP scores 100.

    Args:
        normalized_power: The workout's normalized power in watts, or None.
        intensity_factor: The workout's intensity factor, or None.
        moving_time: The workout's moving time.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.

    Returns:
        The training stress score, or None if normalized_power or
        intensity_factor or ftp_watts is missing.

    >>> from datetime import timedelta
    >>> round(training_stress_score(182.0, 0.867, timedelta(hours=1), 210), 1)
    75.1
    """
    if normalized_power is None or intensity_factor is None or ftp_watts is None:
        return None
    seconds = moving_time.total_seconds()
    return (seconds * normalized_power * intensity_factor) / (ftp_watts * 3600) * 100


def variability_index(
    normalized_power: float | None, avg_power: float | None
) -> float | None:
    """Compute the Variability Index: how much NP exceeds the plain average.

    A steady effort has NP close to avg_power (VI near 1.0); frequent surges
    (e.g. criteriums, interval sessions) push NP, and so VI, higher.

    Args:
        normalized_power: The workout's normalized power in watts, or None.
        avg_power: The workout's average power in watts, or None.

    Returns:
        normalized_power / avg_power, or None if either input is missing or
        avg_power is zero.

    >>> round(variability_index(182.0, 129.0), 4)
    1.4109
    >>> variability_index(182.0, 0.0) is None
    True
    """
    if normalized_power is None or not avg_power:
        return None
    return normalized_power / avg_power


@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
def trimp(
    records: list[RecordPoint], hr_rest: int | None, hr_max: int | None
) -> float | None:
    """Compute Banister's Training Impulse (male exponential weighting).

    TRIMP sums, over each interval between consecutive heart-rate samples,
    ``duration_min x HRr x 0.64 x e**(1.92 x HRr)`` where
    ``HRr = (heart_rate - hr_rest) / (hr_max - hr_rest)`` is the fraction of
    heart-rate reserve used. The exponential weighting means a minute at a
    high HRr counts for much more than a minute at a low one. Gaps wider
    than a normal recording interval (auto-pause, lost signal) contribute no
    impulse, matching how moving_time already excludes them.

    Args:
        records: Time-ordered records of a workout.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The training impulse, or None if hr_rest or hr_max is missing, or
        fewer than two heart-rate samples are available.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start + timedelta(seconds=i), heart_rate=140)
    ...     for i in range(60)
    ... ]
    >>> round(trimp(records, hr_rest=50, hr_max=190), 1)
    1.4
    """
    if hr_rest is None or hr_max is None:
        return None

    heart_rates = [
        (r.timestamp, r.heart_rate) for r in records if r.heart_rate is not None
    ]
    if len(heart_rates) < 2:
        return None

    hr_reserve_range = hr_max - hr_rest
    total = 0.0
    for (earlier_time, earlier_hr), (later_time, later_hr) in pairwise(heart_rates):
        gap = later_time - earlier_time
        if gap > PAUSE_GAP_THRESHOLD:
            continue
        duration_min = gap.total_seconds() / 60
        avg_hr = (earlier_hr + later_hr) / 2
        hr_reserve = (avg_hr - hr_rest) / hr_reserve_range
        male_scale, male_exponent = _TRIMP_MALE_CONSTANTS
        total += (
            duration_min
            * hr_reserve
            * male_scale
            * math.exp(male_exponent * hr_reserve)
        )

    return total


@deal.pre(lambda _: _.ftp_watts is None or _.ftp_watts > 0)
@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
def training_load(
    workout: Workout,
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> float | None:
    """Compute a single workout's training load for the calendar view.

    Prefers TSS (Coggan), since it is scaled to the athlete's own
    threshold power; falls back to TRIMP when the workout has no usable
    power data (no power meter, or too few samples for Normalized Power)
    or no FTP is known.

    Args:
        workout: The workout to score.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown; must be positive if given.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The training load (TSS or TRIMP, whichever was computable), or
        None if neither could be computed.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> workout = Workout(
    ...     start_time=start,
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(timestamp=start + timedelta(seconds=i), power=200)
    ...         for i in range(30)
    ...     ],
    ... )
    >>> round(training_load(workout, ftp_watts=210, hr_rest=50, hr_max=190), 1)
    0.7
    """
    np = normalized_power(workout.records)
    if np is not None and ftp_watts is not None:
        iff = intensity_factor(np, ftp_watts)
        moving_time = compute_workout_metrics(workout).moving_time
        tss = training_stress_score(np, iff, moving_time, ftp_watts)
        if tss is not None:
            return tss

    return trimp(workout.records, hr_rest, hr_max)
