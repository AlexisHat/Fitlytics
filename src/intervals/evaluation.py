"""Metrics for judging detected interval blocks against known ground truth.

These compare two plain lists of time intervals — a reference (from the
synthetic ride generator, or later a hand-labelled real ride) and a
detected set (the segmentation algorithm's output) — without knowing
anything about how either side was produced. That keeps them equally
usable once real detection exists (M3/M4), not just against synthetic
fixtures built for this milestone.
"""

from datetime import datetime
from typing import NamedTuple

import deal
from pydantic import BaseModel, NonNegativeInt

from analysis import average


class Interval(NamedTuple):
    """A time interval, identified only by its start and end.

    Attributes:
        start: Start of the interval.
        end: End of the interval; must be after ``start`` wherever an
            ``Interval`` is used below — enforced by those functions'
            contracts, not here, since a plain ``NamedTuple`` cannot
            validate itself.
    """

    start: datetime
    end: datetime


@deal.pre(lambda a, b: a.start < a.end and b.start < b.end)
@deal.ensure(lambda _: 0.0 <= _.result <= 1.0)
def iou(a: Interval, b: Interval) -> float:
    """Compute the Intersection over Union of two time intervals.

    Args:
        a: The first interval; must have ``start < end``.
        b: The second interval; must have ``start < end``.

    Returns:
        The overlap between ``a`` and ``b`` divided by their combined
        span, from 0.0 (no overlap) to 1.0 (identical intervals).

    Raises:
        deal.PreContractError: If either interval has ``start >= end``.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> a = Interval(start, start + timedelta(seconds=10))
    >>> b = Interval(start + timedelta(seconds=5), start + timedelta(seconds=15))
    >>> round(iou(a, b), 3)
    0.333
    >>> iou(a, a)
    1.0
    >>> iou(a, Interval(start + timedelta(seconds=20), start + timedelta(seconds=30)))
    0.0
    """
    overlap_start = max(a.start, b.start)
    overlap_end = min(a.end, b.end)
    overlap = max((overlap_end - overlap_start).total_seconds(), 0.0)
    a_span = (a.end - a.start).total_seconds()
    b_span = (b.end - b.start).total_seconds()
    union = a_span + b_span - overlap
    return overlap / union if union > 0 else 0.0


class IntervalEvaluation(BaseModel):
    """Result of comparing detected interval blocks against a reference.

    Attributes:
        true_positives: Number of detected blocks matched to a reference
            block (IoU at or above the threshold, one-to-one).
        false_positives: Detected blocks matched to no reference block —
            the count that matters most for a ride with no real intervals
            at all, where every detection is a false alarm.
        false_negatives: Reference blocks matched to no detected block.
        precision: ``true_positives / (true_positives + false_positives)``,
            or None if nothing was detected.
        recall: ``true_positives / (true_positives + false_negatives)``, or
            None if the reference was empty.
        mean_start_offset_s: Mean absolute difference between matched
            blocks' start times, in seconds, or None without any match.
        mean_end_offset_s: Mean absolute difference between matched
            blocks' end times, in seconds, or None without any match.
    """

    true_positives: NonNegativeInt
    false_positives: NonNegativeInt
    false_negatives: NonNegativeInt
    precision: float | None
    recall: float | None
    mean_start_offset_s: float | None
    mean_end_offset_s: float | None


@deal.pre(lambda _: 0 < _.iou_threshold <= 1)
@deal.ensure(
    lambda _: _.result.true_positives + _.result.false_positives == len(_.detected)
)
@deal.ensure(
    lambda _: _.result.true_positives + _.result.false_negatives == len(_.reference)
)
def evaluate(
    reference: list[Interval], detected: list[Interval], iou_threshold: float = 0.5
) -> IntervalEvaluation:
    """Match detected interval blocks against a reference and score them.

    Matching is greedy by descending IoU: the highest-overlap pair is
    matched first, then the next highest among what remains, and so on,
    stopping once no pair reaches ``iou_threshold``. Each block matches at
    most one counterpart on the other side.

    Args:
        reference: The known-correct interval blocks; may be empty (a ride
            with no intervals at all).
        detected: The segmentation algorithm's output; may be empty.
        iou_threshold: Minimum IoU for two blocks to count as a match;
            must be in (0, 1].

    Returns:
        The match counts and derived precision/recall/offset metrics.

    Raises:
        deal.PreContractError: If ``iou_threshold`` is not in (0, 1].

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> ref = [Interval(start, start + timedelta(seconds=60))]
    >>> det = [Interval(start + timedelta(seconds=2), start + timedelta(seconds=61))]
    >>> result = evaluate(ref, det)
    >>> result.true_positives, result.false_positives, result.false_negatives
    (1, 0, 0)
    >>> result.mean_start_offset_s, result.mean_end_offset_s
    (2.0, 1.0)
    """
    pairs = sorted(
        (
            (iou(ref, det), ref_index, det_index)
            for ref_index, ref in enumerate(reference)
            for det_index, det in enumerate(detected)
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )

    matched_ref: set[int] = set()
    matched_det: set[int] = set()
    start_offsets: list[float] = []
    end_offsets: list[float] = []
    for score, ref_index, det_index in pairs:
        if score < iou_threshold:
            break
        if ref_index in matched_ref or det_index in matched_det:
            continue
        matched_ref.add(ref_index)
        matched_det.add(det_index)
        ref, det = reference[ref_index], detected[det_index]
        start_offsets.append(abs((det.start - ref.start).total_seconds()))
        end_offsets.append(abs((det.end - ref.end).total_seconds()))

    true_positives = len(matched_ref)
    false_positives = len(detected) - true_positives
    false_negatives = len(reference) - true_positives
    positives = true_positives + false_positives
    expected = true_positives + false_negatives

    return IntervalEvaluation(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=true_positives / positives if positives > 0 else None,
        recall=true_positives / expected if expected > 0 else None,
        mean_start_offset_s=average(start_offsets) if start_offsets else None,
        mean_end_offset_s=average(end_offsets) if end_offsets else None,
    )
