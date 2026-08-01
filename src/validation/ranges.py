"""Plausibility ranges for measured values, and the check that applies them.

These bounds are physiological, not definitional: a heart rate of 250 bpm is
not impossible by definition, it is implausible for a recorded session and in
practice a chest-strap artefact. Limits that follow from the quantity itself —
a percentage cannot exceed 100, a distance cannot be negative — belong to the
models instead, where breaking one invalidates the whole record.

The upper bounds are deliberately generous. They are meant to catch dropouts
and spikes, not to judge an athlete: the strongest recorded track sprints peak
near 2000 W, so anything above that is the sensor talking, not the rider.
"""

from typing import Final

import deal

Bounds = tuple[float, float]
"""An inclusive ``(low, high)`` range of plausible values."""

HEART_RATE_BPM: Final[Bounds] = (20.0, 240.0)
"""Below 20 the strap has lost contact; above 240 is beyond human range."""

POWER_W: Final[Bounds] = (0.0, 2000.0)
"""Zero means coasting; the upper bound sits above any human sprint peak."""

CADENCE_RPM: Final[Bounds] = (0.0, 200.0)
"""Zero means not pedalling; sustained cadence stays far below the maximum."""

SPEED_MS: Final[Bounds] = (0.0, 40.0)
"""40 m/s is 144 km/h — faster than any descent, so it is a GPS glitch."""

GRADE_PCT: Final[Bounds] = (-40.0, 40.0)
"""The steepest paved roads worldwide sit near 35%; beyond that is a
barometer/GPS artefact rather than a real gradient."""

RESTING_HR_BPM: Final[Bounds] = (20.0, 120.0)
"""Trained endurance athletes reach the low 30s; 20 is the safety margin."""

HRV_MS: Final[Bounds] = (1.0, 300.0)
"""Whoop reports RMSSD, which stays well under 300 ms even when recovered."""

SKIN_TEMP_C: Final[Bounds] = (20.0, 45.0)
"""Skin is cooler than the core; outside this range the strap was off."""

RESPIRATORY_RATE: Final[Bounds] = (5.0, 40.0)
"""Breaths per minute during sleep, where the measurement is taken."""


@deal.pre(lambda low, high, value: low <= high)
@deal.ensure(lambda _: _.result is None or _.low <= _.result <= _.high)
def keep_within(low: float, high: float, value: float | None) -> float | None:
    """Keep a measured value if it is plausible, otherwise discard it.

    Args:
        low: Lower bound of the plausible range, inclusive.
        high: Upper bound of the plausible range, inclusive; must not be
            below ``low``.
        value: The measured value, or None if nothing was measured.

    Returns:
        ``value`` if it lies within the bounds, otherwise None.

    >>> keep_within(*HEART_RATE_BPM, 142)
    142
    >>> keep_within(*HEART_RATE_BPM, 250) is None
    True
    >>> keep_within(*HEART_RATE_BPM, None) is None
    True
    >>> keep_within(*POWER_W, 0)
    0
    """
    if value is None:
        return None
    return value if low <= value <= high else None
