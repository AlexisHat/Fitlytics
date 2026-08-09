"""Tests for intervals.synthetic."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from intervals.synthetic import RideSegment, build_ride

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_build_ride_emits_one_record_per_second_of_a_plain_segment() -> None:
    segments = [RideSegment(duration_s=10, target_power_w=100.0)]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(records) == 10
    assert [r.timestamp for r in records] == [
        START + timedelta(seconds=i) for i in range(10)
    ]
    assert reference == []


def test_build_ride_is_deterministic_for_the_same_seed() -> None:
    segments = [RideSegment(duration_s=30, target_power_w=200.0, noise_std_w=15.0)]
    first, _ = build_ride(segments, seed=42, start=START)
    second, _ = build_ride(segments, seed=42, start=START)
    assert [r.power for r in first] == [r.power for r in second]


def test_build_ride_different_seeds_yield_different_noise() -> None:
    segments = [RideSegment(duration_s=30, target_power_w=200.0, noise_std_w=15.0)]
    first, _ = build_ride(segments, seed=1, start=START)
    second, _ = build_ride(segments, seed=2, start=START)
    assert [r.power for r in first] != [r.power for r in second]


def test_build_ride_marks_a_single_interval_segment_as_one_reference() -> None:
    segments = [
        RideSegment(duration_s=5, target_power_w=100.0),
        RideSegment(duration_s=20, target_power_w=250.0, is_interval=True),
        RideSegment(duration_s=5, target_power_w=100.0),
    ]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(reference) == 1
    assert reference[0].start == START + timedelta(seconds=5)
    assert reference[0].end == START + timedelta(seconds=25)


def test_build_ride_merges_adjacent_interval_segments() -> None:
    segments = [
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
        RideSegment(duration_s=10, target_power_w=0.0, is_interval=True),
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
    ]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(reference) == 1
    assert reference[0].start == START
    assert reference[0].end == START + timedelta(seconds=130)


def test_build_ride_keeps_separated_intervals_apart() -> None:
    segments = [
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
        RideSegment(duration_s=60, target_power_w=100.0),
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
    ]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(reference) == 2


def test_build_ride_a_gap_emits_no_records_and_advances_time() -> None:
    segments = [
        RideSegment(duration_s=10, target_power_w=100.0),
        RideSegment(duration_s=30, target_power_w=None),
        RideSegment(duration_s=10, target_power_w=100.0),
    ]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(records) == 20
    assert records[10].timestamp - records[9].timestamp == timedelta(seconds=31)


def test_build_ride_a_gap_always_splits_reference_intervals() -> None:
    segments = [
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
        RideSegment(duration_s=30, target_power_w=None),
        RideSegment(duration_s=60, target_power_w=250.0, is_interval=True),
    ]
    records, reference = build_ride(segments, seed=1, start=START)
    assert len(reference) == 2


def test_build_ride_rejects_empty_segments() -> None:
    with pytest.raises(deal.PreContractError):
        build_ride([], seed=1)
