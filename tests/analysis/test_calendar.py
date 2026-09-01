"""Tests for analysis.calendar."""

from datetime import UTC, date, datetime, timedelta

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from analysis.calendar import (
    build_calendar,
    daily_training_load,
    training_load_intensity_pct,
)
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


def test_build_calendar_returns_a_full_month_of_rest_days_for_no_workouts() -> None:
    calendar = build_calendar([], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190)

    assert len(calendar) == 31
    assert all(day.training_load == 0.0 and day.workouts == () for day in calendar)
    assert calendar[0].date == date(2026, 7, 1)
    assert calendar[-1].date == date(2026, 7, 31)


def test_build_calendar_covers_every_day_of_a_shorter_month() -> None:
    calendar = build_calendar([], 2026, 2, ftp_watts=None, hr_rest=50, hr_max=190)

    assert [day.date for day in calendar] == [
        date(2026, 2, 1) + timedelta(days=offset) for offset in range(28)
    ]


def test_build_calendar_ignores_workouts_outside_the_month() -> None:
    other_month = _heart_rate_workout(datetime(2026, 8, 1, 8, 0, 0, tzinfo=UTC))

    calendar = build_calendar(
        [other_month], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert all(day.workouts == () for day in calendar)


def test_build_calendar_rest_day_has_zero_load_and_no_workouts() -> None:
    day_one = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))
    day_three = _heart_rate_workout(datetime(2026, 7, 18, 9, 0, 0, tzinfo=UTC))

    calendar = build_calendar(
        [day_one, day_three], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    rest_day = calendar[16]
    assert rest_day.date == date(2026, 7, 17)
    assert rest_day.training_load == 0.0
    assert rest_day.workouts == ()


def test_build_calendar_keeps_the_days_workouts_for_click_through() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    calendar = build_calendar(
        [workout], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert calendar[15].workouts == (workout,)


def test_build_calendar_sums_multiple_workouts_on_the_same_day() -> None:
    morning = _heart_rate_workout(datetime(2026, 7, 16, 7, 0, 0, tzinfo=UTC))
    evening = _heart_rate_workout(datetime(2026, 7, 16, 18, 0, 0, tzinfo=UTC))

    combined = build_calendar(
        [morning, evening], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )
    morning_only = build_calendar(
        [morning], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )
    evening_only = build_calendar(
        [evening], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert combined[15].training_load == pytest.approx(
        morning_only[15].training_load + evening_only[15].training_load
    )
    assert len(combined[15].workouts) == 2


def test_build_calendar_uses_the_utc_date_of_start_time() -> None:
    """A workout just after midnight UTC lands on that UTC day, even if a
    local timezone would put its start on the previous day — there is no
    local timezone in the FIT data to convert with."""
    just_after_midnight = _heart_rate_workout(
        datetime(2026, 7, 17, 0, 30, 0, tzinfo=UTC)
    )

    calendar = build_calendar(
        [just_after_midnight], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert calendar[16].workouts == (just_after_midnight,)


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

    calendar = build_calendar(
        [workout], 2026, 7, ftp_watts=None, hr_rest=None, hr_max=None
    )

    assert calendar[15].training_load == 0.0


def test_build_calendar_clamps_a_negative_trimp_to_zero() -> None:
    """TRIMP can go negative if the recorded heart rate dips below
    hr_rest; a negative training load makes no sense on the calendar."""
    workout = _heart_rate_workout(
        datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC), heart_rate=40
    )
    load = training_load(workout, ftp_watts=None, hr_rest=50, hr_max=190)
    assert load is not None
    assert load < 0

    calendar = build_calendar(
        [workout], 2026, 7, ftp_watts=None, hr_rest=50, hr_max=190
    )

    assert calendar[15].training_load == 0.0


def test_build_calendar_rejects_hr_rest_not_below_hr_max() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    with pytest.raises(deal.PreContractError):
        build_calendar([workout], 2026, 7, ftp_watts=None, hr_rest=190, hr_max=190)


def test_build_calendar_rejects_a_non_positive_ftp() -> None:
    workout = _heart_rate_workout(datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC))

    with pytest.raises(deal.PreContractError):
        build_calendar([workout], 2026, 7, ftp_watts=0, hr_rest=None, hr_max=None)


def test_build_calendar_rejects_an_out_of_range_month() -> None:
    with pytest.raises(deal.PreContractError):
        build_calendar([], 2026, 13, ftp_watts=None, hr_rest=None, hr_max=None)


def test_build_calendar_rejects_a_year_outside_the_date_range() -> None:
    with pytest.raises(deal.PreContractError):
        build_calendar([], 0, 2, ftp_watts=None, hr_rest=None, hr_max=None)


def test_training_load_intensity_pct_rest_day_is_zero() -> None:
    assert training_load_intensity_pct(0.0) == 0


def test_training_load_intensity_pct_scales_linearly_to_the_reference_tss() -> None:
    percentages = [
        training_load_intensity_pct(value) for value in (0.0, 62.5, 125.0, 250.0)
    ]

    assert percentages == [0, 25, 50, 100]


def test_training_load_intensity_pct_caps_above_the_reference_tss() -> None:
    assert training_load_intensity_pct(500.0) == 100


def test_training_load_intensity_pct_stays_within_bounds() -> None:
    for value in (0.0, 10.0, 500.0, 1000.0, 20.0, 30.0):
        assert 0 <= training_load_intensity_pct(value) <= 100


def test_training_load_intensity_pct_rejects_a_negative_value() -> None:
    with pytest.raises(deal.PreContractError):
        training_load_intensity_pct(-1.0)


@given(value=st.floats(min_value=0, max_value=1e6, allow_nan=False))
def test_training_load_intensity_pct_is_always_within_bounds(value: float) -> None:
    assert 0 <= training_load_intensity_pct(value) <= 100


def test_daily_training_load_leaves_out_days_without_a_workout() -> None:
    trained = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    loads = daily_training_load(
        [_heart_rate_workout(trained)], None, hr_rest=50, hr_max=190
    )

    assert list(loads) == [date(2026, 7, 16)]


def test_daily_training_load_sums_two_workouts_on_the_same_day() -> None:
    morning = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    evening = datetime(2026, 7, 16, 18, 0, tzinfo=UTC)
    single = daily_training_load(
        [_heart_rate_workout(morning)], None, hr_rest=50, hr_max=190
    )

    both = daily_training_load(
        [_heart_rate_workout(morning), _heart_rate_workout(evening)],
        None,
        hr_rest=50,
        hr_max=190,
    )

    assert both[date(2026, 7, 16)] == pytest.approx(2 * single[date(2026, 7, 16)])


def test_daily_training_load_is_ordered_by_date_whatever_the_input_order() -> None:
    later = _heart_rate_workout(datetime(2026, 7, 20, 8, 0, tzinfo=UTC))
    earlier = _heart_rate_workout(datetime(2026, 7, 16, 8, 0, tzinfo=UTC))

    loads = daily_training_load([later, earlier], None, hr_rest=50, hr_max=190)

    assert list(loads) == [date(2026, 7, 16), date(2026, 7, 20)]


def test_daily_training_load_drops_a_workout_whose_load_cannot_be_computed() -> None:
    start = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    without_sensors = _workout(start, [RecordPoint(timestamp=start)])

    loads = daily_training_load([without_sensors], None, hr_rest=None, hr_max=None)

    assert loads == {}


def test_daily_training_load_agrees_with_the_calendar_for_the_same_day() -> None:
    start = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    workout = _heart_rate_workout(start)

    loads = daily_training_load([workout], None, hr_rest=50, hr_max=190)
    calendar = build_calendar([workout], 2026, 7, None, hr_rest=50, hr_max=190)

    assert loads[date(2026, 7, 16)] == pytest.approx(calendar[15].training_load)


def test_daily_training_load_rejects_a_non_positive_ftp() -> None:
    with pytest.raises(deal.PreContractError):
        daily_training_load([], 0, hr_rest=50, hr_max=190)
