"""Tests for app.calendar_view's pure grid-layout and intensity-colour helpers."""

from datetime import UTC, date, datetime

from analysis.calendar import CalendarDay
from app.calendar_view import (
    _DARK_TEXT_THRESHOLD_PCT,
    _default_month,
    _grid_weeks,
    _intensity_color,
    _intensity_label,
    _profile_missing,
    _readable_text_color,
    _shift_month,
    _week_start,
)
from models import RecordPoint, Workout


def _day(day: date) -> CalendarDay:
    return CalendarDay(date=day, training_load=0.0, workouts=())


def _workout(start_time: datetime) -> Workout:
    return Workout(
        start_time=start_time,
        sport="cycling",
        records=[RecordPoint(timestamp=start_time, power=200)],
    )


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


def test_intensity_color_is_light_blue_at_zero_percent() -> None:
    assert _intensity_color(0) == "#dbeafe"


def test_intensity_color_is_dark_blue_at_hundred_percent() -> None:
    assert _intensity_color(100) == "#172554"


def test_intensity_color_gets_monotonically_darker() -> None:
    colors = [_intensity_color(pct) for pct in range(0, 101, 10)]

    assert colors == sorted(colors, reverse=True)


def test_intensity_label_covers_rest_day_and_every_quarter() -> None:
    assert _intensity_label(0) == "Ruhetag"
    assert _intensity_label(25) == "leicht"
    assert _intensity_label(50) == "moderat"
    assert _intensity_label(75) == "hart"
    assert _intensity_label(100) == "extrem hart"


def test_readable_text_color_switches_at_the_threshold() -> None:
    assert _readable_text_color(_DARK_TEXT_THRESHOLD_PCT - 1) == "#31333F"
    assert _readable_text_color(_DARK_TEXT_THRESHOLD_PCT) == "#FFFFFF"


def test_profile_missing_when_neither_ftp_nor_hr_profile_is_set() -> None:
    assert _profile_missing(None, None, None) is True


def test_profile_missing_when_hr_profile_is_only_half_set() -> None:
    assert _profile_missing(None, 50, None) is True
    assert _profile_missing(None, None, 190) is True


def test_profile_not_missing_with_ftp_alone() -> None:
    assert _profile_missing(210, None, None) is False


def test_profile_not_missing_with_a_full_hr_profile() -> None:
    assert _profile_missing(None, 50, 190) is False


def test_shift_month_forward_crosses_into_the_next_year() -> None:
    assert _shift_month(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_shift_month_backward_crosses_into_the_previous_year() -> None:
    assert _shift_month(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_shift_month_ignores_the_reference_days_day_of_month() -> None:
    assert _shift_month(date(2026, 7, 16), 1) == date(2026, 8, 1)


def test_shift_month_by_zero_stays_on_the_same_month() -> None:
    assert _shift_month(date(2026, 7, 16), 0) == date(2026, 7, 1)


def test_default_month_is_the_latest_workouts_month() -> None:
    earlier = _workout(datetime(2026, 5, 1, tzinfo=UTC))
    latest = _workout(datetime(2026, 7, 16, tzinfo=UTC))

    assert _default_month([earlier, latest]) == date(2026, 7, 1)
