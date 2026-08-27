"""Tests for app.day_view's pure helpers."""

from datetime import UTC, datetime, timedelta

import pytest

from app.day_view import _has_power_zone_data, _offers_interval_analysis
from models import RecordPoint, Workout, WorkoutCategory

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(category: WorkoutCategory | None = None) -> Workout:
    return Workout(
        start_time=_START,
        sport="cycling",
        category=category,
        records=[RecordPoint(timestamp=_START, power=200)],
    )


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
