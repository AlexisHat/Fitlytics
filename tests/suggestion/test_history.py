"""Tests for suggestion.history."""

from datetime import UTC, date, datetime, timedelta

import deal
import pytest

from intervals import IntervalType
from models import RecordPoint, Workout, WorkoutCategory
from suggestion.history import (
    SessionSummary,
    recent_sessions,
    session_interval_type,
)

TODAY = date(2026, 7, 20)


def _steady_ride(
    day: int,
    category: WorkoutCategory | None = WorkoutCategory.GRUNDLAGE,
    power: int = 150,
    minutes: int = 10,
    ftp_watts: int | None = 250,
) -> Workout:
    """A ride holding one long, perfectly steady effort at ``power``."""
    start = datetime(2026, 7, day, 9, 0, tzinfo=UTC)
    return Workout(
        start_time=start,
        sport="cycling",
        category=category,
        ftp_watts=ftp_watts,
        records=[
            RecordPoint(timestamp=start + timedelta(seconds=i), power=power)
            for i in range(minutes * 60)
        ],
    )


def _interval_ride(day: int, work_power: int, ftp_watts: int | None = 250) -> Workout:
    """A ride alternating easy riding with four hard four-minute blocks."""
    start = datetime(2026, 7, day, 9, 0, tzinfo=UTC)
    powers: list[int] = []
    for _ in range(4):
        powers.extend([120] * 240)
        powers.extend([work_power] * 240)
    powers.extend([120] * 240)
    return Workout(
        start_time=start,
        sport="cycling",
        category=WorkoutCategory.INTERVALLE,
        ftp_watts=ftp_watts,
        records=[
            RecordPoint(timestamp=start + timedelta(seconds=i), power=power)
            for i, power in enumerate(powers)
        ],
    )


def test_only_interval_sessions_are_typed() -> None:
    """Every ride has a hardest stretch; on an endurance ride that is a
    climb, and typing it would invent intervals that were never ridden."""
    endurance = _steady_ride(1, category=WorkoutCategory.GRUNDLAGE)

    assert session_interval_type(endurance, 250) is None


def test_an_untagged_session_is_not_typed() -> None:
    assert session_interval_type(_steady_ride(1, category=None), 250) is None


def test_an_interval_session_is_typed_from_its_blocks() -> None:
    ride = _interval_ride(1, work_power=250)

    assert session_interval_type(ride, 250) is IntervalType.SCHWELLE


def test_the_workouts_own_ftp_decides_the_type() -> None:
    """The same watts are a different kind of session depending on the FTP
    they are measured against."""
    ride = _interval_ride(1, work_power=250, ftp_watts=210)

    assert session_interval_type(ride, 250) is IntervalType.VO2MAX


def test_without_any_ftp_no_type() -> None:
    ride = _interval_ride(1, work_power=250, ftp_watts=None)

    assert session_interval_type(ride, None) is None


def test_duplicate_timestamps_do_not_crash_the_typing() -> None:
    """Real FIT files only guarantee non-decreasing timestamps, which the
    detection pipeline rejects as a contract violation."""
    start = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    ride = Workout(
        start_time=start,
        sport="cycling",
        category=WorkoutCategory.INTERVALLE,
        ftp_watts=250,
        records=[RecordPoint(timestamp=start, power=200)] * 2,
    )

    assert session_interval_type(ride, 250) is None


def test_an_interval_session_without_detectable_blocks() -> None:
    ride = _steady_ride(1, category=WorkoutCategory.INTERVALLE, minutes=1)

    assert session_interval_type(ride, 250) is None


def test_recent_sessions_keeps_only_the_window() -> None:
    rides = [_steady_ride(day) for day in range(1, 9)]

    sessions = recent_sessions(rides, TODAY, window_size=5)

    assert [session.date.day for session in sessions] == [4, 5, 6, 7, 8]


def test_recent_sessions_returns_them_oldest_first() -> None:
    rides = [_steady_ride(3), _steady_ride(1), _steady_ride(2)]

    sessions = recent_sessions(rides, TODAY)

    assert [session.date.day for session in sessions] == [1, 2, 3]


def test_recent_sessions_includes_a_ride_from_today() -> None:
    rides = [_steady_ride(TODAY.day)]

    assert len(recent_sessions(rides, TODAY)) == 1


def test_recent_sessions_ignores_the_future() -> None:
    """A workout dated after today can only come from a device with a wrong
    clock; counting it would describe training that has not happened."""
    rides = [_steady_ride(TODAY.day + 1)]

    assert recent_sessions(rides, TODAY) == []


def test_recent_sessions_on_an_empty_history() -> None:
    assert recent_sessions([], TODAY) == []


def test_recent_sessions_with_fewer_rides_than_the_window() -> None:
    sessions = recent_sessions([_steady_ride(1), _steady_ride(2)], TODAY)

    assert len(sessions) == 2


def test_recent_sessions_carries_the_category_and_type() -> None:
    sessions = recent_sessions([_interval_ride(1, work_power=250)], TODAY)

    assert sessions == [
        SessionSummary(
            date=date(2026, 7, 1),
            category=WorkoutCategory.INTERVALLE,
            interval_type=IntervalType.SCHWELLE,
        )
    ]


def test_recent_sessions_rejects_a_non_positive_window() -> None:
    with pytest.raises(deal.PreContractError):
        recent_sessions([_steady_ride(1)], TODAY, window_size=0)
