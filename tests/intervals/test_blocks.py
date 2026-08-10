"""Tests for intervals.blocks."""

from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest

from intervals.blocks import build_interval_block, build_interval_blocks

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
