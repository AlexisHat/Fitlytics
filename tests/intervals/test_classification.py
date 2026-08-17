"""Tests for intervals.classification."""

from datetime import UTC, datetime, timedelta

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals.blocks import IntervalBlock
from intervals.classification import (
    IntervalType,
    classify_block,
    classify_relative_power,
    classify_session,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _block(relative_power: float | None) -> IntervalBlock:
    return IntervalBlock(
        start=START,
        end=START + timedelta(minutes=8),
        duration=timedelta(minutes=8),
        avg_power_w=220.0,
        avg_power_relative_to_ftp=relative_power,
        avg_heart_rate=None,
        heart_rate_drift_bpm=None,
        evenness=0.95,
    )


@pytest.mark.parametrize(
    ("relative_power", "expected"),
    [
        (0.50, IntervalType.TEMPO),
        (0.80, IntervalType.TEMPO),
        (0.90, IntervalType.SWEET_SPOT),
        (1.00, IntervalType.SCHWELLE),
        (1.10, IntervalType.VO2MAX),
        (1.40, IntervalType.ANAEROB),
    ],
)
def test_classify_relative_power_inside_each_band(
    relative_power: float, expected: IntervalType
) -> None:
    assert classify_relative_power(relative_power) is expected


@pytest.mark.parametrize(
    ("upper_bound", "expected"),
    [
        (0.84, IntervalType.TEMPO),
        (0.97, IntervalType.SWEET_SPOT),
        (1.05, IntervalType.SCHWELLE),
        (1.20, IntervalType.VO2MAX),
    ],
)
def test_a_band_owns_its_upper_bound(
    upper_bound: float, expected: IntervalType
) -> None:
    """Each band is closed at the top, so a power landing exactly on a
    boundary must not slip into the band above it."""
    assert classify_relative_power(upper_bound) is expected


def test_just_above_a_bound_falls_into_the_next_band() -> None:
    assert classify_relative_power(0.8401) is IntervalType.SWEET_SPOT


def test_classify_relative_power_rejects_a_negative_power() -> None:
    with pytest.raises(deal.PreContractError):
        classify_relative_power(-0.1)


def test_classify_block_uses_the_blocks_relative_power() -> None:
    assert classify_block(_block(0.88)) is IntervalType.SWEET_SPOT


def test_classify_block_without_an_ftp() -> None:
    """The bands are defined relative to FTP, so without it there is
    nothing to compare against — no guessed label."""
    assert classify_block(_block(None)) is None


def test_a_session_takes_the_type_most_of_its_blocks_share() -> None:
    blocks = [_block(1.00), _block(1.00), _block(0.90)]

    assert classify_session(blocks) is IntervalType.SCHWELLE


def test_a_single_block_decides_its_own_session() -> None:
    assert classify_session([_block(1.10)]) is IntervalType.VO2MAX


def test_a_unanimous_session_keeps_its_type() -> None:
    blocks = [_block(0.90), _block(0.92), _block(0.88)]

    assert classify_session(blocks) is IntervalType.SWEET_SPOT


def test_two_blocks_of_different_type_are_mixed() -> None:
    """A genuine tie has no majority to report."""
    assert classify_session([_block(1.00), _block(0.90)]) is IntervalType.GEMISCHT


def test_three_blocks_of_three_types_are_mixed() -> None:
    blocks = [_block(0.80), _block(0.90), _block(1.00)]

    assert classify_session(blocks) is IntervalType.GEMISCHT


def test_a_minority_block_does_not_make_a_session_mixed() -> None:
    """Repetitions ridden near a band edge scatter across two bands;
    calling the session mixed would hide what it plainly was."""
    blocks = [_block(0.96), _block(0.95), _block(0.98)]

    assert classify_session(blocks) is IntervalType.SWEET_SPOT


def test_blocks_without_an_ftp_are_skipped_not_counted() -> None:
    blocks = [_block(1.10), _block(None), _block(None)]

    assert classify_session(blocks) is IntervalType.VO2MAX


def test_a_session_without_any_ftp_has_no_type() -> None:
    assert classify_session([_block(None), _block(None)]) is None


def test_classify_session_rejects_an_empty_session() -> None:
    with pytest.raises(deal.PreContractError):
        classify_session([])


@given(relative_power=st.floats(min_value=0.0, max_value=10.0))
def test_every_non_negative_power_gets_a_type(relative_power: float) -> None:
    """The bands cover the whole range without a hole, so no power can
    reach the unreachable fallback at the end of the loop."""
    assert classify_relative_power(relative_power) in set(IntervalType)


@given(relative_power=st.floats(min_value=0.0, max_value=10.0))
def test_a_single_power_is_never_classified_as_mixed(relative_power: float) -> None:
    """GEMISCHT describes a session, never one effort."""
    assert classify_relative_power(relative_power) is not IntervalType.GEMISCHT


@given(
    relative_powers=st.lists(
        st.floats(min_value=0.1, max_value=3.0), min_size=1, max_size=20
    )
)
def test_a_session_is_typed_whenever_any_block_is(
    relative_powers: list[float],
) -> None:
    blocks = [_block(power) for power in relative_powers]

    assert classify_session(blocks) is not None
