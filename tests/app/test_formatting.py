"""Tests for app.formatting."""

from datetime import timedelta

from app.formatting import format_interval_type, format_minutes, format_optional
from intervals import IntervalType


def test_format_optional_distinguishes_zero_from_missing() -> None:
    """A genuine 0 reading (e.g. coasting at 0 W) must not render as '–'."""
    assert format_optional(0.0, "{:.0f} W") == "0 W"
    assert format_optional(None, "{:.0f} W") == "–"


def test_format_optional_applies_the_template() -> None:
    assert format_optional(147.5, "{:.0f} bpm") == "148 bpm"
    assert format_optional(-3.2, "{:+.1f} bpm") == "-3.2 bpm"


def test_format_minutes_without_a_sign() -> None:
    assert format_minutes(timedelta(minutes=4, seconds=30)) == "4.5 min"


def test_format_minutes_always_shows_the_sign_of_a_deviation() -> None:
    """The sign carries the meaning — short or long — so a deviation of
    exactly zero must still read as a deviation, not as a bare number."""
    assert format_minutes(timedelta(minutes=1), signed=True) == "+1.0 min"
    assert format_minutes(timedelta(minutes=-1), signed=True) == "-1.0 min"
    assert format_minutes(timedelta(0), signed=True) == "+0.0 min"


def test_format_interval_type_names_the_type() -> None:
    assert format_interval_type(IntervalType.SWEET_SPOT) == "Sweet Spot"


def test_format_interval_type_without_a_type() -> None:
    """Without an FTP value there is no type, and the table must show that
    rather than an invented label."""
    assert format_interval_type(None) == "–"


def test_every_interval_type_has_a_label() -> None:
    """A missing entry would raise a KeyError in the middle of rendering."""
    for interval_type in IntervalType:
        assert format_interval_type(interval_type)
