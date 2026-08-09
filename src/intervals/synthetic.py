"""Synthetic rides with known interval boundaries, for testing detection.

A hand-labelled real ride is expensive to produce and still only checks one
specific case. A generator that *starts* from known block boundaries makes
segmentation errors exactly measurable (against :mod:`intervals.evaluation`)
without labelling anything by hand — the ground truth is whatever the
generator was asked to build.
"""

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import NamedTuple

import deal

from intervals.evaluation import Interval
from models import RecordPoint

_DEFAULT_START: datetime = datetime(2026, 1, 1, tzinfo=UTC)


class RideSegment(NamedTuple):
    """One constant-target-power stretch of a synthetic ride.

    Attributes:
        duration_s: Length of the segment in seconds; must be positive.
        target_power_w: The power to aim for, before noise and drift, or
            None for a recording gap (no records emitted at all).
        is_interval: Whether this segment counts as part of a ground-truth
            interval block. Consecutive ``is_interval`` segments merge into
            a single reference block — e.g. a real ride's brief coast at a
            red light, marked ``is_interval`` on both sides and on the dip
            itself, still yields one continuous block, matching how a short
            stop shouldn't split a real interval either.
        noise_std_w: Standard deviation of Gaussian noise added to each
            second's power; 0 for a noise-free segment.
        drift_w: Total linear change in target power from the segment's
            first second to its last, e.g. for a fading effort.
    """

    duration_s: int
    target_power_w: float | None
    is_interval: bool = False
    noise_std_w: float = 0.0
    drift_w: float = 0.0


@deal.pre(lambda segments, seed, start=None: len(segments) > 0)
@deal.ensure(lambda _: all(a.end <= b.start for a, b in pairwise(_.result[1])))
def build_ride(
    segments: Sequence[RideSegment], seed: int, start: datetime | None = None
) -> tuple[list[RecordPoint], list[Interval]]:
    """Build a synthetic ride's records and its ground-truth interval blocks.

    Args:
        segments: The ride's segments in order; must not be empty.
        seed: Seed for the noise's random generator, for a reproducible
            ride from the same segments.
        start: Timestamp of the first record; defaults to an arbitrary
            fixed date.

    Returns:
        A pair ``(records, reference)``: one record per second for every
        non-gap segment (a gap segment advances time without emitting any
        records), and the reference interval blocks — one per maximal run
        of consecutive ``is_interval`` segments, chronologically sorted and
        non-overlapping.

    Raises:
        deal.PreContractError: If ``segments`` is empty.

    >>> from datetime import UTC, datetime
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> segments = [
    ...     RideSegment(duration_s=5, target_power_w=100.0),
    ...     RideSegment(duration_s=5, target_power_w=250.0, is_interval=True),
    ... ]
    >>> records, reference = build_ride(segments, seed=1, start=start)
    >>> len(records)
    10
    >>> len(reference)
    1
    >>> reference[0].start.second, reference[0].end.second
    (5, 10)
    """
    start = start if start is not None else _DEFAULT_START
    rng = random.Random(seed)
    records: list[RecordPoint] = []
    reference: list[Interval] = []
    current = start
    run_start: datetime | None = None

    for segment in segments:
        segment_start = current
        if segment.target_power_w is None:
            if run_start is not None:
                reference.append(Interval(run_start, current))
                run_start = None
            current += timedelta(seconds=segment.duration_s)
            continue

        for i in range(segment.duration_s):
            drift = segment.drift_w * (i / max(segment.duration_s - 1, 1))
            noise = rng.gauss(0.0, segment.noise_std_w)
            power = max(0, round(segment.target_power_w + drift + noise))
            records.append(RecordPoint(timestamp=current, power=power))
            current += timedelta(seconds=1)

        if segment.is_interval:
            run_start = run_start if run_start is not None else segment_start
        elif run_start is not None:
            reference.append(Interval(run_start, segment_start))
            run_start = None

    if run_start is not None:
        reference.append(Interval(run_start, current))

    return records, reference
