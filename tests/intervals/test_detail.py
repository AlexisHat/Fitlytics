"""Tests for intervals.detail."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import deal
import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.blocks import IntervalBlock
from intervals.detail import block_detail, slice_block

START = datetime(2026, 1, 1, tzinfo=UTC)


def _series(
    powers: Sequence[int | None],
    cadences: Sequence[int | None] | None = None,
    heart_rates: Sequence[int | None] | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [START + timedelta(seconds=i) for i in range(len(powers))],
            "power": list(powers),
            "cadence": list(cadences) if cadences is not None else [None] * len(powers),
            "heart_rate": (
                list(heart_rates) if heart_rates is not None else [None] * len(powers)
            ),
        }
    )


def _block(start_second: int, end_second: int) -> IntervalBlock:
    start = START + timedelta(seconds=start_second)
    end = START + timedelta(seconds=end_second)
    return IntervalBlock(
        start=start,
        end=end,
        duration=end - start,
        avg_power_w=200.0,
        avg_power_relative_to_ftp=None,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=1.0,
    )


def test_slice_block_keeps_only_the_blocks_own_rows() -> None:
    series = _series([100, 200, 210, 220, 100])

    assert slice_block(series, _block(1, 4))["power"].to_list() == [200, 210, 220]


def test_slice_block_excludes_the_end_second() -> None:
    """``block.end`` is the second after the block's last recorded one, so
    two adjacent blocks must not both claim the row at that second."""
    series = _series([100, 200, 300, 400])

    first = slice_block(series, _block(0, 2))["power"].to_list()
    second = slice_block(series, _block(2, 4))["power"].to_list()

    assert first == [100, 200]
    assert second == [300, 400]


def test_slice_block_covers_a_block_running_to_the_last_recorded_second() -> None:
    """Detection may end a block on the ride's very last row, where
    ``block.end`` points one second past the series."""
    series = _series([100, 200, 300])

    assert slice_block(series, _block(1, 3))["power"].to_list() == [200, 300]


def test_slice_block_rejects_a_block_from_another_workout() -> None:
    series = _series([100, 200, 300])
    elsewhere = _block(90, 120)

    with pytest.raises(deal.PreContractError):
        slice_block(series, elsewhere)


def test_slice_block_rejects_an_empty_series() -> None:
    empty = _series([])

    with pytest.raises(deal.PreContractError):
        slice_block(empty, _block(0, 2))


def test_block_detail_reports_the_peak_second() -> None:
    detail = block_detail(_series([200, 400, 210]))

    assert detail.max_power_w == 400.0


def test_block_detail_averages_cadence() -> None:
    detail = block_detail(_series([200, 200, 200], cadences=[88, 90, 92]))

    assert detail.avg_cadence == pytest.approx(90.0)


def test_block_detail_reports_the_heart_rate_endpoints() -> None:
    detail = block_detail(
        _series([200, 200, 200, 200], heart_rates=[140, 148, 152, 158])
    )

    assert (detail.heart_rate_start, detail.heart_rate_end) == (140.0, 158.0)


def test_block_detail_uses_the_recorded_endpoints_not_the_missing_ones() -> None:
    """A dropout at the block's edge must not be read as the athlete's
    heart rate there — the first and last *recorded* beats are."""
    detail = block_detail(
        _series([200, 200, 200, 200], heart_rates=[None, 145, 155, None])
    )

    assert (detail.heart_rate_start, detail.heart_rate_end) == (145.0, 155.0)


def test_block_detail_without_a_cadence_sensor() -> None:
    detail = block_detail(_series([200, 200]))

    assert detail.avg_cadence is None


def test_block_detail_without_a_heart_rate_sensor() -> None:
    detail = block_detail(_series([200, 200]))

    assert (detail.heart_rate_start, detail.heart_rate_end) == (None, None)


def test_block_detail_ignores_a_recording_gap_in_the_power_trace() -> None:
    detail = block_detail(_series([200, None, 260]))

    assert detail.max_power_w == 260.0


def test_block_detail_rejects_a_block_without_any_power_reading() -> None:
    with pytest.raises(deal.PreContractError):
        block_detail(_series([None, None]))


@given(
    powers=st.lists(st.integers(min_value=0, max_value=2000), min_size=1, max_size=200)
)
def test_peak_power_is_never_below_the_blocks_average(powers: list[int]) -> None:
    """The maximum of a set is an upper bound on its mean, so a close-up
    can never make an interval look weaker than the block report does."""
    detail = block_detail(_series(list(powers)))

    assert detail.max_power_w >= sum(powers) / len(powers)


@given(
    cadences=st.lists(st.integers(min_value=0, max_value=200), min_size=1, max_size=200)
)
def test_average_cadence_lies_within_the_recorded_range(cadences: list[int]) -> None:
    detail = block_detail(
        _series([200] * len(cadences), cadences=list(cadences)),
    )

    assert detail.avg_cadence is not None
    assert min(cadences) <= detail.avg_cadence <= max(cadences)
