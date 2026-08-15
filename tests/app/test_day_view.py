"""Tests for app.day_view's pure helpers."""

from datetime import UTC, datetime, timedelta

import pytest

from app.day_view import (
    _format_minutes,
    _format_optional,
    _has_power_zone_data,
    _has_strictly_increasing_timestamps,
    _offers_interval_analysis,
)
from models import RecordPoint, Workout, WorkoutCategory

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(category: WorkoutCategory | None = None) -> Workout:
    return Workout(
        start_time=_START,
        sport="cycling",
        category=category,
        records=[RecordPoint(timestamp=_START, power=200)],
    )


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


def test_has_power_zone_data_requires_an_ftp() -> None:
    records = [
        RecordPoint(timestamp=_START + timedelta(seconds=i), power=200)
        for i in range(3)
    ]

    assert _has_power_zone_data(records, ftp_watts=None) is False


def test_has_power_zone_data_requires_two_power_samples() -> None:
    records = [RecordPoint(timestamp=_START, power=200)]

    assert _has_power_zone_data(records, ftp_watts=210) is False


def test_has_power_zone_data_true_with_ftp_and_enough_samples() -> None:
    records = [
        RecordPoint(timestamp=_START + timedelta(seconds=i), power=200)
        for i in range(3)
    ]

    assert _has_power_zone_data(records, ftp_watts=210) is True


def test_offers_interval_analysis_only_for_an_interval_session() -> None:
    assert _offers_interval_analysis(_workout(WorkoutCategory.INTERVALLE)) is True


@pytest.mark.parametrize(
    "category",
    [
        WorkoutCategory.GRUNDLAGE,
        WorkoutCategory.GROUPRIDE,
        WorkoutCategory.RECOVERY,
        WorkoutCategory.SONSTIGE,
    ],
)
def test_offers_no_interval_analysis_for_other_categories(
    category: WorkoutCategory,
) -> None:
    """An endurance ride has climbs, and detection would happily report
    them — true, but not what the athlete asked about."""
    assert _offers_interval_analysis(_workout(category)) is False


def test_offers_no_interval_analysis_without_a_category() -> None:
    assert _offers_interval_analysis(_workout()) is False


def test_format_minutes_without_a_sign() -> None:
    assert _format_minutes(timedelta(minutes=4, seconds=30)) == "4.5 min"


def test_format_minutes_always_shows_the_sign_of_a_deviation() -> None:
    """The sign carries the meaning — short or long — so a deviation of
    exactly zero must still read as a deviation, not as a bare number."""
    assert _format_minutes(timedelta(minutes=1), signed=True) == "+1.0 min"
    assert _format_minutes(timedelta(minutes=-1), signed=True) == "-1.0 min"
    assert _format_minutes(timedelta(0), signed=True) == "+0.0 min"
