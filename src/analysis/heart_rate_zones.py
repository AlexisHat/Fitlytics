"""Heart-rate zone distribution during a workout's moving time.

Zones are defined by the Karvonen method — percentage of heart-rate
reserve, HRR = (heart_rate - hr_rest) / (hr_max - hr_rest) — rather than a
plain percentage of hr_max. HRR accounts for the athlete's own resting
heart rate, so two athletes sharing the same hr_max but different aerobic
bases (and so different hr_rest) get zones reflecting their actual relative
effort, not just a fraction of one number.

This individualization is also why the device's own hr_zone/time_in_hr_zone
session fields are not used here: checked against a real recording, the
device's zone boundaries (139/159/173/187 bpm) do not correspond to round
percentages of this athlete's actual hr_max (203 bpm) at all — 68.5/78.3/
85.2/92.1%, not the expected 60/70/80/90 — so they were evidently set from a
different, unknown, and possibly outdated basis. Recomputing from the
athlete's current hr_rest/hr_max is precisely the advantage Fitlytics has
over trusting an opaque device configuration.
"""

from datetime import timedelta
from itertools import pairwise

import deal
from pydantic import BaseModel

from analysis.workout import PAUSE_GAP_THRESHOLD
from models import RecordPoint

_ZONE_UPPER_BOUNDS_PCT = (0.60, 0.70, 0.80, 0.90)
"""Upper bound of heart-rate-reserve zones 1-4; zone 5 is anything above."""


class HeartRateZoneDistribution(BaseModel):
    """Time spent in each of the 5 Karvonen heart-rate zones.

    Covers moving time only: paused stretches contribute to no zone, the
    same as elsewhere in the analysis.

    Attributes:
        zone_1: Time with heart-rate reserve below 60% (very light).
        zone_2: Time with heart-rate reserve 60-70% (light).
        zone_3: Time with heart-rate reserve 70-80% (moderate).
        zone_4: Time with heart-rate reserve 80-90% (hard).
        zone_5: Time with heart-rate reserve 90% and above (maximum).
    """

    zone_1: timedelta
    zone_2: timedelta
    zone_3: timedelta
    zone_4: timedelta
    zone_5: timedelta


def _hr_zone(hr_reserve: float) -> int:
    """Classify a heart-rate-reserve fraction into one of 5 Karvonen zones.

    Args:
        hr_reserve: Fraction of heart-rate reserve used; not clamped, so
            values below 0 or above 1 are valid (a brief dip below hr_rest,
            or a sprint above hr_max) and fall into zone 1 or zone 5.

    Returns:
        The zone number, 1 to 5.

    >>> _hr_zone(0.5)
    1
    >>> _hr_zone(0.95)
    5
    """
    for zone, upper_bound in enumerate(_ZONE_UPPER_BOUNDS_PCT, start=1):
        if hr_reserve < upper_bound:
            return zone
    return 5


def _has_non_negative_zone_durations(
    result: HeartRateZoneDistribution | None,
) -> bool:
    """Helper for deals. Return whether all returned zone durations are non-negative."""
    if result is None:
        return True

    return all(
        duration >= timedelta(0)
        for duration in (
            result.zone_1,
            result.zone_2,
            result.zone_3,
            result.zone_4,
            result.zone_5,
        )
    )


@deal.pre(lambda _: _.hr_rest is None or _.hr_max is None or _.hr_rest < _.hr_max)
@deal.pre(
    lambda _: all(
        earlier.timestamp <= later.timestamp for earlier, later in pairwise(_.records)
    )
)
@deal.post(_has_non_negative_zone_durations)
def heart_rate_zone_distribution(
    records: list[RecordPoint], hr_rest: int | None, hr_max: int | None
) -> HeartRateZoneDistribution | None:
    """Compute time spent in each Karvonen heart-rate zone during a workout.

    Each interval between two consecutive heart-rate samples is credited
    to the zone of its earlier reading (a sample-and-hold step function,
    matching how most fitness devices compute time-in-zone). Gaps wider
    than a normal recording interval (auto-pause, lost signal) contribute
    to no zone, matching how moving_time already excludes them.

    hr_rest and hr_max are not read from anywhere automatically — a
    configured athlete profile or per-day Whoop resting heart rate is a
    later, separate decision (see docs/entscheidungen.md); here they are
    plain parameters, so a missing profile yields None instead of failing.

    Args:
        records: Time-ordered records of a workout.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The time-in-zone distribution, or None if hr_rest or hr_max is
        missing, or fewer than two heart-rate samples are available.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start, heart_rate=100),
    ...     RecordPoint(timestamp=start + timedelta(seconds=1), heart_rate=180),
    ...     RecordPoint(timestamp=start + timedelta(seconds=2), heart_rate=180),
    ... ]
    >>> zones = heart_rate_zone_distribution(records, hr_rest=50, hr_max=200)
    >>> zones.zone_1, zones.zone_4
    (datetime.timedelta(seconds=1), datetime.timedelta(seconds=1))
    """
    if hr_rest is None or hr_max is None:
        return None

    heart_rates = [
        (r.timestamp, r.heart_rate) for r in records if r.heart_rate is not None
    ]
    if len(heart_rates) < 2:
        return None

    hr_reserve_range = hr_max - hr_rest
    zone_durations = [timedelta(0)] * 5
    for (earlier_time, earlier_hr), (later_time, _) in pairwise(heart_rates):
        gap = later_time - earlier_time
        if gap > PAUSE_GAP_THRESHOLD:
            continue
        hr_reserve = (earlier_hr - hr_rest) / hr_reserve_range
        zone_durations[_hr_zone(hr_reserve) - 1] += gap

    return HeartRateZoneDistribution(
        zone_1=zone_durations[0],
        zone_2=zone_durations[1],
        zone_3=zone_durations[2],
        zone_4=zone_durations[3],
        zone_5=zone_durations[4],
    )
