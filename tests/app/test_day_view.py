"""Tests for app.day_view's pure helpers."""

from datetime import UTC, datetime, timedelta

from app.day_view import _has_strictly_increasing_timestamps
from models import RecordPoint

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


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
