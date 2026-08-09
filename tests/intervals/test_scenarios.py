"""Tests for intervals.scenarios — the eight mandatory synthetic rides."""

from itertools import pairwise

from intervals.evaluation import Interval
from intervals.scenarios import (
    clean_5x4min,
    noisy_5x4min_with_fatigue,
    recording_gap_mid_block,
    rolling_terrain_no_intervals,
    single_1min_block_in_warmup,
    ten_by_30s_with_pauses,
    traffic_light_stop_mid_block,
    two_by_20min,
)


def _duration_s(interval: Interval) -> float:
    return (interval.end - interval.start).total_seconds()


def test_clean_5x4min_has_five_four_minute_blocks() -> None:
    _, reference = clean_5x4min()
    assert len(reference) == 5
    assert all(_duration_s(block) == 240 for block in reference)


def test_noisy_5x4min_with_fatigue_has_five_four_minute_blocks() -> None:
    _, reference = noisy_5x4min_with_fatigue()
    assert len(reference) == 5
    assert all(_duration_s(block) == 240 for block in reference)


def test_ten_by_30s_with_pauses_has_ten_thirty_second_blocks() -> None:
    _, reference = ten_by_30s_with_pauses()
    assert len(reference) == 10
    assert all(_duration_s(block) == 30 for block in reference)


def test_two_by_20min_has_two_twenty_minute_blocks() -> None:
    _, reference = two_by_20min()
    assert len(reference) == 2
    assert all(_duration_s(block) == 1200 for block in reference)


def test_single_1min_block_in_warmup_has_exactly_one_block() -> None:
    _, reference = single_1min_block_in_warmup()
    assert len(reference) == 1
    assert _duration_s(reference[0]) == 60


def test_rolling_terrain_has_no_reference_blocks_at_all() -> None:
    _, reference = rolling_terrain_no_intervals()
    assert reference == []


def test_traffic_light_stop_yields_one_block_not_three() -> None:
    _, reference = traffic_light_stop_mid_block()
    assert len(reference) == 1
    assert _duration_s(reference[0]) == 240 + 12 + 240


def test_recording_gap_splits_into_two_blocks_and_a_real_gap() -> None:
    records, reference = recording_gap_mid_block()
    assert len(reference) == 2
    assert all(_duration_s(block) == 240 for block in reference)
    gaps = [
        (later.timestamp - earlier.timestamp).total_seconds()
        for earlier, later in pairwise(records)
    ]
    assert max(gaps) > 1.0
