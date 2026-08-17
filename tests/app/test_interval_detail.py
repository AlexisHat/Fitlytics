"""Tests for app.interval_detail's pure helpers."""

from app.interval_detail import _BUTTONS_PER_ROW, button_rows


def test_a_short_session_fits_in_one_row() -> None:
    assert button_rows(3) == [[1, 2, 3]]


def test_a_long_session_wraps_onto_a_second_row() -> None:
    assert button_rows(_BUTTONS_PER_ROW + 2) == [
        list(range(1, _BUTTONS_PER_ROW + 1)),
        [_BUTTONS_PER_ROW + 1, _BUTTONS_PER_ROW + 2],
    ]


def test_a_full_row_does_not_start_an_empty_next_one() -> None:
    assert button_rows(_BUTTONS_PER_ROW) == [list(range(1, _BUTTONS_PER_ROW + 1))]


def test_no_buttons_without_detected_blocks() -> None:
    assert button_rows(0) == []


def test_every_block_gets_exactly_one_button() -> None:
    """A block without a button would be unreachable, and a number shown
    twice would open the wrong block."""
    count = _BUTTONS_PER_ROW * 3 + 1

    numbers = [number for row in button_rows(count) for number in row]

    assert numbers == list(range(1, count + 1))
