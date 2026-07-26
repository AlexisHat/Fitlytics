"""Tests for models.types."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from models import RecordPoint

BERLIN = timezone(timedelta(hours=2))


def test_utc_datetime_rejects_naive_value() -> None:
    with pytest.raises(PydanticValidationError, match="naive"):
        RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39))


def test_utc_datetime_keeps_utc_value_unchanged() -> None:
    point = RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))

    assert point.timestamp == datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)


def test_utc_datetime_converts_other_offset_to_utc() -> None:
    point = RecordPoint(timestamp=datetime(2026, 7, 23, 1, 43, 25, tzinfo=BERLIN))

    assert point.timestamp == datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC)
    assert point.timestamp.tzinfo == UTC


def test_utc_datetime_conversion_preserves_the_instant() -> None:
    berlin_time = datetime(2026, 7, 23, 1, 43, 25, tzinfo=BERLIN)

    point = RecordPoint(timestamp=berlin_time)

    assert point.timestamp == berlin_time
