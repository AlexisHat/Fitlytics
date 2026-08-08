"""Tests for analysis.calendar."""

from datetime import UTC, date, datetime, timedelta

import deal
import pytest

from analysis.calendar import build_calendar
from analysis.load import training_load
from models import RecordPoint, Workout


def _workout(start_time: datetime, records: list[RecordPoint]) -> Workout:
    return Workout(start_time=start_time, sport="cycling", records=records)


def _heart_rate_workout(start_time: datetime, heart_rate: int = 140) -> Workout:
    return _workout(
        start_time,
        [
            RecordPoint(
                timestamp=start_time + timedelta(seconds=i), heart_rate=heart_rate
            )
            for i in range(60)
        ],
    )


def test_build_calendar_returns_empty_for_no_workouts() -> None:
    assert build_calendar([], ftp_watts=None, hr_rest=50, hr_max=190) == ()


def test_build_calendar_covers_the_full_range_including_rest_days() -> None:
    day_one = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))
    day_three = _heart_rate_workout(datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC))

    calendar = build_calendar(
        [day_one, day_three], ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert [day.date for day in calendar] == [
        date(2026, 7, 16),
        date(2026, 7, 17),
        date(2026, 7, 18),
    ]


def test_build_calendar_rest_day_has_zero_load_and_no_workouts() -> None:
    day_one = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))
    day_three = _heart_rate_workout(datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC))

    calendar = build_calendar(
        [day_one, day_three], ftp_watts=None, hr_rest=50, hr_max=190
    )

    rest_day = calendar[1]
    assert rest_day.date == date(2026, 7, 17)
    assert rest_day.training_load == 0.0
    assert rest_day.workouts == ()


def test_build_calendar_keeps_the_days_workouts_for_click_through() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    calendar = build_calendar([workout], ftp_watts=None, hr_rest=50, hr_max=190)

    assert calendar[0].workouts == (workout,)


def test_build_calendar_sums_multiple_workouts_on_the_same_day() -> None:
    morning = _heart_rate_workout(datetime(2026, 7, 16, 7, 0, 0, tzinfo=UTC))
    evening = _heart_rate_workout(datetime(2026, 7, 16, 18, 0, 0, tzinfo=UTC))

    combined = build_calendar(
        [morning, evening], ftp_watts=None, hr_rest=50, hr_max=190
    )
    morning_only = build_calendar([morning], ftp_watts=None, hr_rest=50, hr_max=190)
    evening_only = build_calendar([evening], ftp_watts=None, hr_rest=50, hr_max=190)

    assert combined[0].training_load == pytest.approx(
        morning_only[0].training_load + evening_only[0].training_load
    )
    assert len(combined[0].workouts) == 2


def test_build_calendar_uses_the_utc_date_of_start_time() -> None:
    """A workout just after midnight UTC lands on that UTC day, even if a
    local timezone would put its start on the previous day — there is no
    local timezone in the FIT data to convert with."""
    just_after_midnight = _heart_rate_workout(
        datetime(2026, 7, 17, 0, 30, 0, tzinfo=UTC)
    )

    calendar = build_calendar(
        [just_after_midnight], ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert calendar[0].date == date(2026, 7, 17)


def test_build_calendar_zero_load_when_nothing_is_computable() -> None:
    """A workout without power or a known heart-rate profile can't be
    scored at all — it must not raise, and must not fabricate a load."""
    records = [
        RecordPoint(
            timestamp=datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC) + timedelta(seconds=i)
        )
        for i in range(10)
    ]
    workout = _workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC), records)

    calendar = build_calendar([workout], ftp_watts=None, hr_rest=None, hr_max=None)

    assert calendar[0].training_load == 0.0


def test_build_calendar_clamps_a_negative_trimp_to_zero() -> None:
    """TRIMP can go negative if the recorded heart rate dips below
    hr_rest; a negative training load makes no sense on the calendar."""
    workout = _heart_rate_workout(
        datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC), heart_rate=40
    )
    load = training_load(workout, ftp_watts=None, hr_rest=50, hr_max=190)
    assert load is not None
    assert load < 0

    calendar = build_calendar([workout], ftp_watts=None, hr_rest=50, hr_max=190)

    assert calendar[0].training_load == 0.0


def test_build_calendar_rejects_hr_rest_not_below_hr_max() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    with pytest.raises(deal.PreContractError):
        build_calendar([workout], ftp_watts=None, hr_rest=190, hr_max=190)


def test_build_calendar_rejects_a_non_positive_ftp() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    with pytest.raises(deal.PreContractError):
        build_calendar([workout], ftp_watts=0, hr_rest=None, hr_max=None)
