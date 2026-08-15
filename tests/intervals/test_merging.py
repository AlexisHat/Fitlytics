"""Tests for intervals.merging."""

from collections.abc import Sequence

import polars as pl

from intervals.config import MERGE_GAP_S
from intervals.merging import _merge_pass, _should_merge, merge_candidates


def _series(
    powers: Sequence[float | None], standstill_at: set[int] | None = None
) -> pl.DataFrame:
    standstill_at = standstill_at or set()
    return pl.DataFrame(
        {
            "power": powers,
            "is_standstill": [i in standstill_at for i in range(len(powers))],
        }
    )


def test_should_merge_a_short_gap() -> None:
    series = _series([250.0] * 5 + [150.0] * 5 + [250.0] * 5)
    assert _should_merge(series, (0, 5), (10, 15)) is True


def test_should_not_merge_a_gap_longer_than_the_allowance() -> None:
    long_gap = MERGE_GAP_S + 1
    series = _series([250.0] * 5 + [150.0] * long_gap + [250.0] * 5)
    assert _should_merge(series, (0, 5), (5 + long_gap, 10 + long_gap)) is False


def test_should_merge_a_gap_exactly_at_the_allowance() -> None:
    series = _series([250.0] * 5 + [150.0] * MERGE_GAP_S + [250.0] * 5)
    assert _should_merge(series, (0, 5), (5 + MERGE_GAP_S, 10 + MERGE_GAP_S)) is True


def test_should_not_merge_across_a_standstill_in_the_gap() -> None:
    series = _series([250.0] * 5 + [0.0] * 5 + [250.0] * 5, standstill_at={7})
    assert _should_merge(series, (0, 5), (10, 15)) is False


def test_should_not_merge_across_a_recording_gap() -> None:
    powers: list[float | None] = [250.0] * 5 + [None] * 5 + [250.0] * 5
    assert _should_merge(_series(powers), (0, 5), (10, 15)) is False


def test_should_merge_across_a_deep_but_brief_dip() -> None:
    """The old rule refused to bridge a dip below the local baseline. That
    is exactly what split two real efforts, so a short dip now merges no
    matter how far down it goes."""
    series = _series([250.0] * 5 + [20.0] * 8 + [250.0] * 5)
    assert _should_merge(series, (0, 5), (13, 18)) is True


def test_should_merge_a_zero_length_gap() -> None:
    series = _series([250.0] * 10)
    assert _should_merge(series, (0, 5), (5, 10)) is True


def test_merge_pass_collapses_a_chain_in_one_sweep() -> None:
    series = _series([250.0] * 30)
    assert _merge_pass(series, [(0, 5), (7, 12), (14, 19), (21, 26)]) == [(0, 26)]


def test_merge_candidates_on_an_empty_list() -> None:
    assert merge_candidates(_series([250.0] * 10), []) == []


def test_merge_candidates_keeps_candidates_separated_by_a_standstill() -> None:
    series = _series([400.0] * 30 + [0.0] * 30 + [400.0] * 30, standstill_at={40})
    assert merge_candidates(series, [(0, 30), (60, 90)]) == [(0, 30), (60, 90)]


def test_merge_candidates_keeps_candidates_separated_by_a_long_gap() -> None:
    series = _series([400.0] * 200)
    far_apart = [(0, 30), (30 + MERGE_GAP_S + 1, 100)]
    assert merge_candidates(series, far_apart) == far_apart
