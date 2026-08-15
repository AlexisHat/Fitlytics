"""Tests for intervals.selection."""

from datetime import timedelta

import deal
import polars as pl
import pytest

from intervals.config import KEEP_FRACTION, MIN_BLOCK_DURATION_S
from intervals.evaluation import Interval, evaluate
from intervals.preprocessing import mark_standstill, resample_to_1hz, smooth_power
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
from intervals.selection import (
    _mean_smoothed_power,
    filter_by_duration,
    find_candidates,
    select_consistent,
)
from models import RecordPoint


def _series(smoothed: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"smoothed_power": smoothed})


def _prepared(records: list[RecordPoint]) -> pl.DataFrame:
    return mark_standstill(smooth_power(resample_to_1hz(records)))


def _detected(
    records: list[RecordPoint], candidates: list[tuple[int, int]]
) -> list[Interval]:
    start = records[0].timestamp
    return [
        Interval(start + timedelta(seconds=s), start + timedelta(seconds=e))
        for s, e in candidates
    ]


def test_mean_smoothed_power_averages_only_the_window() -> None:
    series = _series([100.0] * 5 + [300.0] * 5)
    assert _mean_smoothed_power(series, (5, 10)) == 300.0


def test_filter_by_duration_keeps_a_candidate_exactly_at_the_minimum() -> None:
    assert filter_by_duration([(0, MIN_BLOCK_DURATION_S)]) == [
        (0, MIN_BLOCK_DURATION_S)
    ]


def test_filter_by_duration_drops_a_candidate_one_second_too_short() -> None:
    assert filter_by_duration([(0, MIN_BLOCK_DURATION_S - 1)]) == []


def test_filter_by_duration_keeps_order() -> None:
    long_enough = MIN_BLOCK_DURATION_S
    candidates = [(0, long_enough), (500, 510), (1000, 1000 + long_enough)]
    assert filter_by_duration(candidates) == [
        (0, long_enough),
        (1000, 1000 + long_enough),
    ]


def test_select_consistent_drops_a_candidate_far_below_the_strongest() -> None:
    series = _series([100.0] * 5 + [250.0] * 5)
    assert select_consistent(series, [(0, 5), (5, 10)]) == [(5, 10)]


def test_select_consistent_keeps_repetitions_at_a_similar_power() -> None:
    series = _series([250.0] * 5 + [240.0] * 5 + [245.0] * 5)
    candidates = [(0, 5), (5, 10), (10, 15)]
    assert select_consistent(series, candidates) == candidates


def test_select_consistent_keeps_a_candidate_exactly_at_the_cutoff() -> None:
    strongest = 250.0
    series = _series([strongest] * 5 + [strongest * KEEP_FRACTION] * 5)
    assert select_consistent(series, [(0, 5), (5, 10)]) == [(0, 5), (5, 10)]


def test_select_consistent_always_keeps_the_strongest_candidate() -> None:
    """The postcondition in prose: a non-empty input never yields nothing,
    so detection never silently loses the one effort it is surest about."""
    series = _series([10.0] * 5 + [500.0] * 5 + [12.0] * 5)
    assert select_consistent(series, [(0, 5), (5, 10), (10, 15)]) == [(5, 10)]


def test_select_consistent_on_an_empty_list() -> None:
    assert select_consistent(_series([250.0] * 5), []) == []


def test_find_candidates_rejects_an_empty_series() -> None:
    records = [
        RecordPoint(timestamp=clean_5x4min()[0][0].timestamp, power=100),
    ]
    empty = _prepared(records).filter(pl.col("power") > 1000)
    with pytest.raises(deal.PreContractError):
        find_candidates(empty)


def test_find_candidates_returns_nothing_without_any_power_data() -> None:
    """A workout recorded without a power meter cannot be analysed for
    intervals; that is an empty result, not a crash."""
    start = clean_5x4min()[0][0].timestamp
    records = [RecordPoint(timestamp=start + timedelta(seconds=i)) for i in range(600)]

    assert find_candidates(_prepared(records)) == []


def test_find_candidates_finds_all_five_blocks_of_the_clean_scenario() -> None:
    records, reference = clean_5x4min()
    result = evaluate(
        reference, _detected(records, find_candidates(_prepared(records)))
    )

    assert result.true_positives == 5
    assert result.false_positives == 0
    assert result.false_negatives == 0


def test_find_candidates_finds_all_five_blocks_despite_noise_and_fatigue() -> None:
    records, reference = noisy_5x4min_with_fatigue()
    result = evaluate(
        reference, _detected(records, find_candidates(_prepared(records)))
    )

    assert result.true_positives == 5
    assert result.false_positives == 0
    assert result.false_negatives == 0


def test_find_candidates_finds_nothing_on_rolling_terrain() -> None:
    records, reference = rolling_terrain_no_intervals()
    assert reference == []

    assert find_candidates(_prepared(records)) == []


def test_find_candidates_finds_both_blocks_of_a_long_steady_session() -> None:
    records, reference = two_by_20min()
    result = evaluate(
        reference, _detected(records, find_candidates(_prepared(records)))
    )

    assert result.true_positives == 2
    assert result.false_positives == 0


def test_find_candidates_keeps_one_block_across_a_traffic_light_stop() -> None:
    records, reference = traffic_light_stop_mid_block()
    result = evaluate(
        reference, _detected(records, find_candidates(_prepared(records)))
    )

    assert result.true_positives == 1
    assert result.false_positives == 0


def test_find_candidates_handles_a_recording_gap_mid_block() -> None:
    records, reference = recording_gap_mid_block()
    result = evaluate(
        reference, _detected(records, find_candidates(_prepared(records)))
    )

    assert result.true_positives == 2
    assert result.false_positives == 0


def test_find_candidates_does_not_detect_thirty_second_sprints() -> None:
    """A documented limit, not a silent failure: the 30 s smoothing window
    flattens anything of its own length, so blocks shorter than
    ``MIN_BLOCK_DURATION_S`` are out of scope. Detecting them would need a
    second, much shorter smoothing scale — deliberately not built (see
    ``docs/entscheidungen.md``). Reporting nothing is the honest outcome;
    reporting the wrong blocks would be worse."""
    records, reference = ten_by_30s_with_pauses()
    assert len(reference) == 10

    assert find_candidates(_prepared(records)) == []


def test_find_candidates_does_not_detect_a_single_one_minute_block() -> None:
    """The same documented limit as the 30 s sprints above: one minute is
    below ``MIN_BLOCK_DURATION_S``."""
    records, reference = single_1min_block_in_warmup()
    assert len(reference) == 1

    assert find_candidates(_prepared(records)) == []
