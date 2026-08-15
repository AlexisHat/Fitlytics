"""Tests for app.recovery_view's pure helpers."""

from datetime import UTC, date, datetime

from app.recovery_view import PERIOD_DAYS, limit_to_period
from models import RecoveryDay

TODAY = date(2026, 7, 21)


def _day(day: date) -> RecoveryDay:
    return RecoveryDay(
        date=day,
        cycle_start=datetime(day.year, day.month, day.day, 1, 0, tzinfo=UTC),
        recovery_score=70,
        hrv_ms=95.0,
        resting_hr=55,
    )


def test_limit_to_period_keeps_only_the_recent_days() -> None:
    days = [_day(date(2026, 7, d)) for d in (1, 15, 20)]

    kept = limit_to_period(days, 10, TODAY)

    assert [day.date.day for day in kept] == [15, 20]


def test_limit_to_period_keeps_everything_for_none() -> None:
    days = [_day(date(2026, 7, d)) for d in (1, 15, 20)]

    assert limit_to_period(days, None, TODAY) == days


def test_limit_to_period_keeps_the_day_exactly_on_the_boundary() -> None:
    days = [_day(date(2026, 7, 11))]

    assert limit_to_period(days, 10, TODAY) == days


def test_limit_to_period_drops_the_day_just_outside_the_boundary() -> None:
    days = [_day(date(2026, 7, 10))]

    assert limit_to_period(days, 10, TODAY) == []


def test_limit_to_period_counts_back_from_today_not_the_newest_day() -> None:
    """A gap since the last Whoop export must stay visible as a gap, not be
    closed by sliding the window onto the newest stored day."""
    stale = [_day(date(2026, 1, d)) for d in (1, 2, 3)]

    assert limit_to_period(stale, 30, TODAY) == []


def test_limit_to_period_on_an_empty_history() -> None:
    assert limit_to_period([], 30, TODAY) == []


def test_limit_to_period_keeps_chronological_order() -> None:
    days = [_day(date(2026, 7, d)) for d in (15, 16, 17)]

    assert [day.date for day in limit_to_period(days, 30, TODAY)] == [
        date(2026, 7, 15),
        date(2026, 7, 16),
        date(2026, 7, 17),
    ]


def test_every_offered_period_is_usable() -> None:
    """The labels are user-facing; a typo in one would silently offer a
    period that filters everything away."""
    days = [_day(date(2026, 7, 20))]

    for period_days in PERIOD_DAYS.values():
        assert limit_to_period(days, period_days, TODAY) == days
