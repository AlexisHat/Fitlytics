"""Tests for storage.workouts."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from errors import StorageError
from models import PlannedIntervalSpec, RecordPoint, Workout, WorkoutCategory
from storage.schema import init_db
from storage.workouts import load_workouts, save_workout

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _workout(
    start_time: datetime = START,
    ftp_watts: int | None = 210,
    name: str | None = None,
    category: WorkoutCategory | None = None,
    planned_intervals: PlannedIntervalSpec | None = None,
) -> Workout:
    return Workout(
        start_time=start_time,
        name=name,
        category=category,
        planned_intervals=planned_intervals,
        sport="cycling",
        sub_sport="generic",
        ftp_watts=ftp_watts,
        records=[
            RecordPoint(
                timestamp=start_time + timedelta(seconds=i),
                heart_rate=140 + i,
                power=200 + i,
            )
            for i in range(3)
        ],
    )


@pytest.fixture
def conn() -> sqlite3.Connection:
    return init_db(":memory:")


def test_save_workout_reports_a_new_save(conn: sqlite3.Connection) -> None:
    assert save_workout(conn, _workout()) is True


def test_save_workout_skips_an_already_saved_workout(conn: sqlite3.Connection) -> None:
    save_workout(conn, _workout())

    assert save_workout(conn, _workout()) is False


def test_save_workout_does_not_skip_a_different_start_time(
    conn: sqlite3.Connection,
) -> None:
    save_workout(conn, _workout())

    later = _workout(start_time=START + timedelta(days=1))
    assert save_workout(conn, later) is True


def test_load_workouts_roundtrips_workout_fields(conn: sqlite3.Connection) -> None:
    original = _workout()
    save_workout(conn, original)

    loaded = load_workouts(conn)

    assert len(loaded) == 1
    assert loaded[0].start_time == original.start_time
    assert loaded[0].sport == original.sport
    assert loaded[0].sub_sport == original.sub_sport
    assert loaded[0].ftp_watts == original.ftp_watts


def test_load_workouts_roundtrips_records_in_order(conn: sqlite3.Connection) -> None:
    original = _workout()
    save_workout(conn, original)

    loaded = load_workouts(conn)[0]

    assert [r.timestamp for r in loaded.records] == [
        r.timestamp for r in original.records
    ]
    assert [r.heart_rate for r in loaded.records] == [
        r.heart_rate for r in original.records
    ]
    assert [r.power for r in loaded.records] == [r.power for r in original.records]


def test_load_workouts_handles_none_fields(conn: sqlite3.Connection) -> None:
    workout = _workout(ftp_watts=None)
    save_workout(conn, workout)

    loaded = load_workouts(conn)[0]

    assert loaded.ftp_watts is None


def test_load_workouts_roundtrips_a_given_name(conn: sqlite3.Connection) -> None:
    workout = _workout(name="Feierabendrunde")
    save_workout(conn, workout)

    loaded = load_workouts(conn)[0]

    assert loaded.name == "Feierabendrunde"


def test_load_workouts_roundtrips_no_name_as_none(conn: sqlite3.Connection) -> None:
    save_workout(conn, _workout())

    loaded = load_workouts(conn)[0]

    assert loaded.name is None


def test_load_workouts_roundtrips_a_category_without_a_plan(
    conn: sqlite3.Connection,
) -> None:
    workout = _workout(category=WorkoutCategory.GRUNDLAGE)
    save_workout(conn, workout)

    loaded = load_workouts(conn)[0]

    assert loaded.category is WorkoutCategory.GRUNDLAGE
    assert loaded.planned_intervals is None


def test_load_workouts_roundtrips_a_planned_interval_spec(
    conn: sqlite3.Connection,
) -> None:
    plan = PlannedIntervalSpec(
        repetitions=6, duration=timedelta(minutes=4), target_power_w=280
    )
    workout = _workout(category=WorkoutCategory.INTERVALLE, planned_intervals=plan)
    save_workout(conn, workout)

    loaded = load_workouts(conn)[0]

    assert loaded.category is WorkoutCategory.INTERVALLE
    assert loaded.planned_intervals == plan


def test_load_workouts_roundtrips_no_category_as_none(
    conn: sqlite3.Connection,
) -> None:
    save_workout(conn, _workout())

    loaded = load_workouts(conn)[0]

    assert loaded.category is None


def test_load_workouts_returns_empty_list_for_an_empty_database(
    conn: sqlite3.Connection,
) -> None:
    assert load_workouts(conn) == []


def test_load_workouts_orders_by_start_time(conn: sqlite3.Connection) -> None:
    earlier = _workout(start_time=START)
    later = _workout(start_time=START + timedelta(days=1))
    save_workout(conn, later)
    save_workout(conn, earlier)

    loaded = load_workouts(conn)

    assert [w.start_time for w in loaded] == [earlier.start_time, later.start_time]


def test_save_workout_wraps_a_closed_connection_as_storage_error() -> None:
    closed_conn = init_db(":memory:")
    closed_conn.close()

    with pytest.raises(StorageError):
        save_workout(closed_conn, _workout())


def test_load_workouts_wraps_a_closed_connection_as_storage_error() -> None:
    closed_conn = init_db(":memory:")
    closed_conn.close()

    with pytest.raises(StorageError):
        load_workouts(closed_conn)
