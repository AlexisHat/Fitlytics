"""Tests for app.day_view's pure helpers."""

from datetime import UTC, datetime, timedelta

from app.day_view import _format_optional, _has_strictly_increasing_timestamps
from models import RecordPoint

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def test_format_optional_distinguishes_zero_from_missing() -> None:
    """A genuine 0 reading (e.g. coasting at 0 W) must not render as '–'."""
    assert _format_optional(0.0, "{:.0f} W") == "0 W"
    assert _format_optional(None, "{:.0f} W") == "–"


def test_format_optional_applies_the_template() -> None:
    assert _format_optional(147.5, "{:.0f} bpm") == "148 bpm"
    assert _format_optional(-3.2, "{:+.1f} bpm") == "-3.2 bpm"


def test_has_strictly_increasing_timestamps_accepts_a_clean_series() -> None:
    records = [RecordPoint(timestamp=_START + timedelta(seconds=i)) for i in range(5)]

    assert _has_strictly_increasing_timestamps(records) is True


def test_has_strictly_increasing_timestamps_rejects_a_duplicate() -> None:
    records = [
        RecordPoint(timestamp=_START),
        RecordPoint(timestamp=_START),
        RecordPoint(timestamp=_START + timedelta(seconds=1)),
    ]

    assert _has_strictly_increasing_timestamps(records) is False


def test_has_strictly_increasing_timestamps_accepts_a_single_record() -> None:
    assert _has_strictly_increasing_timestamps([RecordPoint(timestamp=_START)]) is True
