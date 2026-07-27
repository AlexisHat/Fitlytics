"""Aerobic efficiency metrics for a single workout.

Neither metric here has a device-computed equivalent: Efficiency Factor and
aerobic decoupling are coaching concepts layered on top of the raw power
and heart-rate stream, not something a bike computer reports.
"""

from analysis.metrics import average
from models import RecordPoint


def efficiency_factor(
    normalized_power: float | None,
    avg_power: float | None,
    avg_heart_rate: float | None,
) -> float | None:
    """Compute the Efficiency Factor: power output per heartbeat.

    Uses normalized_power when available (it accounts for surges, so it
    reflects the workout's true demand better than a plain average), and
    falls back to avg_power otherwise, e.g. for a workout too short for NP's
    30-sample window.

    A rising EF across similar workouts over weeks is a classic sign of
    improving aerobic fitness: the same heart rate now sustains more power.

    Args:
        normalized_power: The workout's normalized power in watts, or None.
        avg_power: The workout's average power in watts, or None.
        avg_heart_rate: The workout's average heart rate in bpm, or None.

    Returns:
        power / avg_heart_rate (preferring normalized_power over avg_power),
        or None if no power figure or no heart rate is available.

    >>> round(efficiency_factor(182.0, 129.0, 151.0), 3)
    1.205
    >>> efficiency_factor(None, 129.0, 151.0) is not None
    True
    >>> efficiency_factor(None, None, 151.0) is None
    True
    """
    power = normalized_power if normalized_power is not None else avg_power
    if power is None or not avg_heart_rate:
        return None
    return power / avg_heart_rate


def _power_to_heart_rate_ratio(records: list[RecordPoint]) -> float | None:
    """Compute the average power-to-heart-rate ratio of a set of records.

    Args:
        records: Records to average over.

    Returns:
        average(power) / average(heart_rate), or None if either measurement
        is entirely missing from ``records``.
    """
    powers = [r.power for r in records if r.power is not None]
    heart_rates = [r.heart_rate for r in records if r.heart_rate is not None]
    if not powers or not heart_rates:
        return None
    return average(powers) / average(heart_rates)


def decoupling_pct(records: list[RecordPoint]) -> float | None:
    """Compute aerobic decoupling: the drift of power-to-heart-rate ratio.

    Splits the records at the midpoint and compares the average
    power-to-heart-rate ratio of the first half against the second. A
    positive result means the same power cost more heartbeats later in the
    workout — a sign of aerobic fatigue; close to 0% indicates a
    well-controlled, sustainable effort.

    Args:
        records: Time-ordered records of a workout.

    Returns:
        The percentage drop from the first-half to the second-half ratio,
        or None if fewer than two records are given, or either half is
        missing power or heart-rate data.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> heart_rates = [140] * 30 + [160] * 30
    >>> records = [
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=i), power=200, heart_rate=hr
    ...     )
    ...     for i, hr in enumerate(heart_rates)
    ... ]
    >>> round(decoupling_pct(records), 2)
    12.5
    """
    if len(records) < 2:
        return None

    midpoint = len(records) // 2
    ratio_first = _power_to_heart_rate_ratio(records[:midpoint])
    ratio_second = _power_to_heart_rate_ratio(records[midpoint:])
    if not ratio_first or ratio_second is None:
        return None

    return (ratio_first - ratio_second) / ratio_first * 100
