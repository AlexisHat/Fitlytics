"""Tests for intervals.blocks."""

import math
from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.blocks import (
    IntervalBlock,
    build_interval_block,
    build_interval_blocks,
    summarize_interval_blocks,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(
    powers: list[int], heart_rates: list[int | None] | None = None
) -> pl.DataFrame:
    heart_rates = heart_rates if heart_rates is not None else [None] * len(powers)
    return pl.DataFrame(
        {
            "timestamp": [START + timedelta(seconds=i) for i in range(len(powers))],
            "power": powers,
            "heart_rate": heart_rates,
        }
    )


def test_build_interval_block_computes_average_power() -> None:
    series = _series([200, 220, 240, 260])
    block = build_interval_block(series, (0, 4))
    assert block.avg_power_w == 230.0


def test_build_interval_block_relative_to_ftp() -> None:
    series = _series([200, 200, 200])
    block = build_interval_block(series, (0, 3), ftp_watts=250)
    assert block.avg_power_relative_to_ftp == pytest.approx(0.8)


def test_build_interval_block_relative_to_ftp_is_none_without_ftp() -> None:
    series = _series([200, 200, 200])
    block = build_interval_block(series, (0, 3))
    assert block.avg_power_relative_to_ftp is None


def test_build_interval_block_duration_and_edges() -> None:
    series = _series([200] * 10)
    block = build_interval_block(series, (2, 8))
    assert block.start == START + timedelta(seconds=2)
    assert block.end == START + timedelta(seconds=8)
    assert block.duration == timedelta(seconds=6)


def test_build_interval_block_handles_a_block_ending_at_the_series_end() -> None:
    # no row exists *after* the block - end must not be looked up there
    series = _series([200] * 5)
    block = build_interval_block(series, (0, 5))
    assert block.end == START + timedelta(seconds=5)


def test_build_interval_block_avg_heart_rate_is_none_without_data() -> None:
    series = _series([200, 200, 200])
    block = build_interval_block(series, (0, 3))
    assert block.avg_heart_rate is None
    assert block.heart_rate_drift_bpm is None


def test_build_interval_block_heart_rate_drift_is_second_half_minus_first() -> None:
    series = _series([200] * 4, heart_rates=[140, 145, 150, 155])
    block = build_interval_block(series, (0, 4))
    assert block.avg_heart_rate == 147.5
    assert block.heart_rate_drift_bpm == 10.0


def test_build_interval_block_evenness_is_perfect_for_constant_power() -> None:
    series = _series([200] * 10)
    block = build_interval_block(series, (0, 10))
    assert block.evenness == 1.0


def test_build_interval_block_evenness_drops_for_variable_power() -> None:
    series = _series([100, 400] * 5)
    block = build_interval_block(series, (0, 10))
    assert block.evenness < 1.0


def test_build_interval_block_rejects_a_malformed_candidate() -> None:
    series = _series([200] * 5)
    with pytest.raises(deal.PreContractError):
        build_interval_block(series, (3, 3))


def test_build_interval_blocks_builds_one_report_per_candidate() -> None:
    series = _series([200] * 20)
    blocks = build_interval_blocks(series, [(0, 5), (10, 15)], ftp_watts=250)
    assert len(blocks) == 2
    assert all(block.avg_power_w == 200.0 for block in blocks)


def test_summarize_interval_blocks_counts_and_spreads_power() -> None:
    series = _series([200] * 5 + [240] * 5)
    blocks = build_interval_blocks(series, [(0, 5), (5, 10)])

    summary = summarize_interval_blocks(blocks)

    assert summary.count == 2
    assert summary.power_spread_w == 40.0
    assert summary.avg_evenness == pytest.approx(1.0)


def test_summarize_interval_blocks_averages_only_the_drifts_that_exist() -> None:
    series = _series([200] * 4, heart_rates=[140, 145, 150, 155])
    with_hr = build_interval_block(series, (0, 4))
    without_hr = build_interval_block(_series([200] * 3), (0, 3))

    summary = summarize_interval_blocks([with_hr, without_hr])

    assert summary.avg_heart_rate_drift_bpm == with_hr.heart_rate_drift_bpm


def test_summarize_interval_blocks_drift_is_none_without_any_heart_rate() -> None:
    series = _series([200] * 10)
    blocks = build_interval_blocks(series, [(0, 5), (5, 10)])

    summary = summarize_interval_blocks(blocks)

    assert summary.avg_heart_rate_drift_bpm is None


def test_summarize_interval_blocks_single_block_has_zero_spread() -> None:
    series = _series([200] * 5)
    blocks = build_interval_blocks(series, [(0, 5)])

    summary = summarize_interval_blocks(blocks)

    assert summary.count == 1
    assert summary.power_spread_w == 0.0


def test_summarize_interval_blocks_rejects_an_empty_list() -> None:
    with pytest.raises(deal.PreContractError):
        summarize_interval_blocks([])


@st.composite
def _interval_blocks(draw: st.DrawFn) -> list[IntervalBlock]:
    """A non-empty list of blocks, varying only what summarize_interval_blocks
    actually reads (avg_power_w, evenness, heart_rate_drift_bpm)."""
    count = draw(st.integers(min_value=1, max_value=8))
    return [
        IntervalBlock(
            start=START,
            end=START + timedelta(minutes=1),
            duration=timedelta(minutes=1),
            avg_power_w=draw(st.floats(min_value=0, max_value=2000, allow_nan=False)),
            avg_power_relative_to_ftp=None,
            avg_heart_rate=None,
            heart_rate_drift_bpm=draw(
                st.one_of(
                    st.none(),
                    st.floats(min_value=-100, max_value=100, allow_nan=False),
                )
            ),
            evenness=draw(st.floats(min_value=0, max_value=1, allow_nan=False)),
        )
        for _ in range(count)
    ]


@given(blocks=_interval_blocks())
def test_summarize_interval_blocks_count_matches_input(
    blocks: list[IntervalBlock],
) -> None:
    assert summarize_interval_blocks(blocks).count == len(blocks)


@given(blocks=_interval_blocks())
def test_summarize_interval_blocks_power_spread_matches_min_max(
    blocks: list[IntervalBlock],
) -> None:
    powers = [block.avg_power_w for block in blocks]

    spread = summarize_interval_blocks(blocks).power_spread_w

    assert spread == pytest.approx(max(powers) - min(powers))
    assert spread >= 0.0


@given(blocks=_interval_blocks())
def test_summarize_interval_blocks_evenness_is_always_between_min_and_max(
    blocks: list[IntervalBlock],
) -> None:
    # math.isclose tolerance, not a strict bound: average() itself only
    # guarantees this up to floating-point rounding (see
    # docs/entscheidungen.md, "Postcondition von average() toleriert
    # Gleitkomma-Rundung").
    evenness_values = [block.evenness for block in blocks]
    low, high = min(evenness_values), max(evenness_values)

    avg_evenness = summarize_interval_blocks(blocks).avg_evenness

    assert (
        (low <= avg_evenness <= high)
        or math.isclose(avg_evenness, low)
        or math.isclose(avg_evenness, high)
    )
