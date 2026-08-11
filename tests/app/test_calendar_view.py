"""Tests for app.calendar_view's pure grid-layout helpers."""

from datetime import date

from analysis.calendar import CalendarDay
from app.calendar_view import _grid_weeks, _week_start


def _day(day: date) -> CalendarDay:
    return CalendarDay(date=day, training_load=0.0, workouts=())


def test_week_start_returns_the_same_monday_for_any_day_in_that_week() -> None:
    monday = date(2026, 7, 13)

    for offset in range(7):
        assert _week_start(date(2026, 7, 13 + offset)) == monday


def test_grid_weeks_pads_a_partial_first_and_last_week_with_none() -> None:
    days = (_day(date(2026, 7, 16)), _day(date(2026, 7, 17)))

    weeks = _grid_weeks(days)

    assert len(weeks) == 1
    thursday, friday = weeks[0][3], weeks[0][4]
    assert thursday is not None
    assert thursday.date == date(2026, 7, 16)
    assert friday is not None
    assert friday.date == date(2026, 7, 17)
    assert weeks[0][0] is None
    assert weeks[0][5] is None
    assert weeks[0][6] is None


def test_grid_weeks_spans_multiple_weeks() -> None:
    days = (_day(date(2026, 7, 16)), _day(date(2026, 7, 23)))

    weeks = _grid_weeks(days)

    assert len(weeks) == 2
