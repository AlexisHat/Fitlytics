"""Tests for models.workout."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError as PydanticValidationError

from models import PlannedIntervalSpec, RecordPoint, Workout, WorkoutCategory


def test_workout_construction_succeeds_with_valid_data() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        sub_sport="generic",
        ftp_watts=210,
        records=[
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), heart_rate=120
            ),
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 40, tzinfo=UTC), heart_rate=121
            ),
        ],
    )

    assert workout.sport == "cycling"
    assert workout.ftp_watts == 210
    assert len(workout.records) == 2


def test_workout_requires_at_least_one_record() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="cycling",
            records=[],
        )


def test_workout_rejects_empty_sport() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="",
            records=[
                RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))
            ],
        )


def test_record_point_accepts_zero_power_and_cadence() -> None:
    """Coasting downhill is a genuine reading, not a missing value."""
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), power=0, cadence=0
    )

    assert point.power == 0
    assert point.cadence == 0


@pytest.mark.parametrize("field", ["heart_rate", "power", "cadence"])
def test_record_point_rejects_negative_measurements(field: str) -> None:
    with pytest.raises(PydanticValidationError):
        RecordPoint(
            timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), **{field: -1}
        )


def test_record_point_allows_negative_altitude() -> None:
    """Below sea level is a real place, not a sensor error."""
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), altitude_m=-4.2
    )

    assert point.altitude_m == -4.2


def test_record_point_allows_negative_grade() -> None:
    """A descent is a real gradient, not a sensor error."""
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), grade_pct=-3.82
    )

    assert point.grade_pct == -3.82


def test_workout_allows_negative_avg_grade() -> None:
    """A net-downhill course is a real profile, not a sensor error."""
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        avg_grade_pct=-1.5,
        records=[RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))],
    )

    assert workout.avg_grade_pct == -1.5


def test_record_point_accepts_boundary_latitude_and_longitude() -> None:
    point = RecordPoint(
        timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        latitude=90.0,
        longitude=-180.0,
    )

    assert point.latitude == 90.0
    assert point.longitude == -180.0


@pytest.mark.parametrize(
    ("field", "value"), [("latitude", 90.1), ("latitude", -90.1), ("longitude", 180.1)]
)
def test_record_point_rejects_out_of_range_position(field: str, value: float) -> None:
    with pytest.raises(PydanticValidationError):
        RecordPoint.model_validate(
            {"timestamp": datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), field: value}
        )


def test_workout_has_gps_track_with_two_or_more_fixes() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        records=[
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
                latitude=51.06,
                longitude=6.85,
            ),
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 40, tzinfo=UTC),
                latitude=51.07,
                longitude=6.86,
            ),
        ],
    )

    assert workout.has_gps_track is True


def test_workout_has_no_gps_track_with_only_one_fix() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        records=[
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
                latitude=51.06,
                longitude=6.85,
            ),
            RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 40, tzinfo=UTC)),
        ],
    )

    assert workout.has_gps_track is False


def test_workout_has_no_gps_track_without_any_fix() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        records=[
            RecordPoint(
                timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC), power=200
            )
        ],
    )

    assert workout.has_gps_track is False


def test_workout_display_name_falls_back_to_the_date_without_a_name() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        records=[RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))],
    )

    assert workout.display_name == "Training am 2026-07-16"


def test_workout_display_name_uses_the_given_name() -> None:
    workout = Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        name="Feierabendrunde",
        records=[RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))],
    )

    assert workout.display_name == "Feierabendrunde"


def test_workout_rejects_negative_total_ascent() -> None:
    with pytest.raises(PydanticValidationError):
        Workout(
            start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
            sport="cycling",
            total_ascent_m=-1.0,
            records=[
                RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))
            ],
        )


def _single_record_workout(**overrides: object) -> Workout:
    return Workout(
        start_time=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC),
        sport="cycling",
        records=[RecordPoint(timestamp=datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC))],
        **overrides,  # type: ignore[arg-type]
    )


def test_workout_accepts_a_category_without_a_plan() -> None:
    workout = _single_record_workout(category=WorkoutCategory.GRUNDLAGE)

    assert workout.category is WorkoutCategory.GRUNDLAGE
    assert workout.planned_intervals is None


def test_workout_accepts_a_matching_category_and_plan() -> None:
    plan = PlannedIntervalSpec(
        repetitions=6, duration=timedelta(minutes=4), target_power_w=280
    )

    workout = _single_record_workout(
        category=WorkoutCategory.INTERVALLE, planned_intervals=plan
    )

    assert workout.planned_intervals == plan


def test_workout_rejects_a_plan_without_the_intervalle_category() -> None:
    plan = PlannedIntervalSpec(
        repetitions=6, duration=timedelta(minutes=4), target_power_w=280
    )

    with pytest.raises(PydanticValidationError):
        _single_record_workout(
            category=WorkoutCategory.GRUNDLAGE, planned_intervals=plan
        )


def test_workout_rejects_a_plan_without_any_category() -> None:
    plan = PlannedIntervalSpec(
        repetitions=6, duration=timedelta(minutes=4), target_power_w=280
    )

    with pytest.raises(PydanticValidationError):
        _single_record_workout(planned_intervals=plan)


@pytest.mark.parametrize(
    "overrides",
    [
        {"repetitions": 0},
        {"repetitions": -1},
        {"target_power_w": 0},
        {"target_power_w": -1},
    ],
)
def test_planned_interval_spec_rejects_non_positive_counts(
    overrides: dict[str, int],
) -> None:
    fields: dict[str, object] = {
        "repetitions": 6,
        "duration": timedelta(minutes=4),
        "target_power_w": 280,
    }
    fields.update(overrides)

    with pytest.raises(PydanticValidationError):
        PlannedIntervalSpec(**fields)  # type: ignore[arg-type]


def test_planned_interval_spec_rejects_a_zero_duration() -> None:
    with pytest.raises(PydanticValidationError):
        PlannedIntervalSpec(repetitions=6, duration=timedelta(0), target_power_w=280)


def test_planned_interval_spec_rejects_a_negative_duration() -> None:
    with pytest.raises(PydanticValidationError):
        PlannedIntervalSpec(
            repetitions=6, duration=timedelta(minutes=-1), target_power_w=280
        )
