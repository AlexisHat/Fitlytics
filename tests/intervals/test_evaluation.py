"""Tests for intervals.evaluation."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from intervals.evaluation import Interval, evaluate, iou

START = datetime(2026, 1, 1, tzinfo=UTC)


def _interval(start_s: int, end_s: int) -> Interval:
    return Interval(
        START + timedelta(seconds=start_s), START + timedelta(seconds=end_s)
    )


def test_iou_of_identical_intervals_is_one() -> None:
    a = _interval(0, 60)
    assert iou(a, a) == 1.0


def test_iou_of_disjoint_intervals_is_zero() -> None:
    assert iou(_interval(0, 10), _interval(20, 30)) == 0.0


def test_iou_of_adjacent_touching_intervals_is_zero() -> None:
    assert iou(_interval(0, 10), _interval(10, 20)) == 0.0


def test_iou_of_partial_overlap() -> None:
    # overlap 5s, union (10 + 10 - 5) = 15s -> 1/3
    assert iou(_interval(0, 10), _interval(5, 15)) == pytest.approx(1 / 3)


def test_iou_rejects_malformed_interval() -> None:
    with pytest.raises(deal.PreContractError):
        iou(_interval(10, 10), _interval(0, 10))


def test_evaluate_perfect_match() -> None:
    ref = [_interval(0, 60)]
    det = [_interval(0, 60)]
    result = evaluate(ref, det)
    assert (result.true_positives, result.false_positives, result.false_negatives) == (
        1,
        0,
        0,
    )
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.mean_start_offset_s == 0.0
    assert result.mean_end_offset_s == 0.0


def test_evaluate_measures_edge_offset_of_a_shifted_match() -> None:
    ref = [_interval(0, 60)]
    det = [_interval(2, 61)]
    result = evaluate(ref, det)
    assert result.true_positives == 1
    assert result.mean_start_offset_s == 2.0
    assert result.mean_end_offset_s == 1.0


def test_evaluate_no_detections_at_all() -> None:
    ref = [_interval(0, 60), _interval(100, 160)]
    result = evaluate(ref, [])
    assert (result.true_positives, result.false_positives, result.false_negatives) == (
        0,
        0,
        2,
    )
    assert result.precision is None
    assert result.recall == 0.0
    assert result.mean_start_offset_s is None
    assert result.mean_end_offset_s is None


def test_evaluate_false_positives_on_a_ride_with_no_real_intervals() -> None:
    det = [_interval(0, 30), _interval(50, 80)]
    result = evaluate([], det)
    assert (result.true_positives, result.false_positives, result.false_negatives) == (
        0,
        2,
        0,
    )
    assert result.precision == 0.0
    assert result.recall is None


def test_evaluate_below_threshold_counts_as_no_match() -> None:
    ref = [_interval(0, 100)]
    det = [_interval(90, 190)]  # overlap 10s, union 190s -> IoU well below 0.5
    result = evaluate(ref, det, iou_threshold=0.5)
    assert result.true_positives == 0
    assert result.false_positives == 1
    assert result.false_negatives == 1


def test_evaluate_matches_are_one_to_one() -> None:
    # one long reference block must not match two overlapping detections
    ref = [_interval(0, 100)]
    det = [_interval(0, 50), _interval(50, 100)]
    result = evaluate(ref, det, iou_threshold=0.1)
    assert result.true_positives <= 1


def test_evaluate_rejects_invalid_threshold() -> None:
    with pytest.raises(deal.PreContractError):
        evaluate([], [], iou_threshold=0.0)
    with pytest.raises(deal.PreContractError):
        evaluate([], [], iou_threshold=1.5)
