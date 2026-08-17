"""Tests for app.day_view's pure helpers."""

from datetime import UTC, datetime, timedelta

import pytest

from app.day_view import (
    _has_power_zone_data,
    _has_strictly_increasing_timestamps,
    _offers_interval_analysis,
    effective_ftp,
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


def test_effective_ftp_prefers_the_workouts_own_value() -> None:
    """A ride's analysis must not rewrite itself when the athlete retests,
    so the value recorded with the ride wins over today's profile."""
    ride = _workout().model_copy(update={"ftp_watts": 210})

    assert effective_ftp(ride, 223) == 210


def test_effective_ftp_falls_back_to_the_profile() -> None:
    """A head unit with no FTP configured leaves the workout without one;
    the profile value is then the only thing available."""
    assert effective_ftp(_workout(), 223) == 223


def test_effective_ftp_without_any_value() -> None:
    assert effective_ftp(_workout(), None) is None


def test_effective_ftp_ignores_the_profile_when_the_workout_has_a_value() -> None:
    ride = _workout().model_copy(update={"ftp_watts": 210})

    assert effective_ftp(ride, None) == 210
