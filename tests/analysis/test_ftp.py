"""Tests for analysis.ftp."""

from datetime import UTC, datetime

from analysis.ftp import effective_ftp
from models import RecordPoint, Workout

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(ftp_watts: int | None = None) -> Workout:
    return Workout(
        start_time=_START,
        sport="cycling",
        ftp_watts=ftp_watts,
        records=[RecordPoint(timestamp=_START, power=200)],
    )


def test_effective_ftp_prefers_the_workouts_own_value() -> None:
    """A ride's analysis must not rewrite itself when the athlete retests,
    so the value recorded with the ride wins over today's profile."""
    ride = _workout(ftp_watts=210)

    assert effective_ftp(ride, 223) == 210


def test_effective_ftp_falls_back_to_the_profile() -> None:
    """A head unit with no FTP configured leaves the workout without one;
    the profile value is then the only thing available."""
    assert effective_ftp(_workout(), 223) == 223


def test_effective_ftp_without_any_value() -> None:
    assert effective_ftp(_workout(), None) is None


def test_effective_ftp_ignores_the_profile_when_the_workout_has_a_value() -> None:
    ride = _workout(ftp_watts=210)

    assert effective_ftp(ride, None) == 210
