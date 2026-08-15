"""Tests for storage.recovery."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from errors import StorageError
from models import RecoveryDay
from storage.recovery import load_recovery_days, save_recovery_days
from storage.schema import init_db

DAY = date(2026, 7, 16)


def _recovery_day(
    day: date = DAY,
    recovery_score: int | None = 73,
    hrv_ms: float | None = 98.0,
    resting_hr: int | None = 57,
) -> RecoveryDay:
    return RecoveryDay(
        date=day,
        cycle_start=datetime(day.year, day.month, day.day, 1, 43, tzinfo=UTC),
        recovery_score=recovery_score,
        resting_hr=resting_hr,
        hrv_ms=hrv_ms,
        skin_temp_c=33.04,
        respiratory_rate=14.9,
        blood_oxygen=96.27,
    )


def test_save_and_load_roundtrips_a_recovery_day() -> None:
    conn = init_db(":memory:")
    save_recovery_days(conn, [_recovery_day()])

    loaded = load_recovery_days(conn)

    assert len(loaded) == 1
    assert loaded[0] == _recovery_day()


def test_load_returns_nothing_from_an_empty_database() -> None:
    assert load_recovery_days(init_db(":memory:")) == []


def test_save_reports_how_many_days_were_written() -> None:
    conn = init_db(":memory:")

    assert (
        save_recovery_days(conn, [_recovery_day(), _recovery_day(date(2026, 7, 17))])
        == 2
    )


def test_save_accepts_an_empty_list() -> None:
    conn = init_db(":memory:")

    assert save_recovery_days(conn, []) == 0
    assert load_recovery_days(conn) == []


def test_reimporting_the_same_day_replaces_it_instead_of_duplicating() -> None:
    """A Whoop export always carries the full history, so the same day
    arrives again on every upload — it must update, not accumulate."""
    conn = init_db(":memory:")
    save_recovery_days(conn, [_recovery_day(recovery_score=73)])

    save_recovery_days(conn, [_recovery_day(recovery_score=81)])
    loaded = load_recovery_days(conn)

    assert len(loaded) == 1
    assert loaded[0].recovery_score == 81


def test_load_returns_days_sorted_oldest_first() -> None:
    conn = init_db(":memory:")
    save_recovery_days(
        conn,
        [
            _recovery_day(date(2026, 7, 18)),
            _recovery_day(date(2026, 7, 16)),
            _recovery_day(date(2026, 7, 17)),
        ],
    )

    loaded = load_recovery_days(conn)

    assert [day.date for day in loaded] == [
        date(2026, 7, 16),
        date(2026, 7, 17),
        date(2026, 7, 18),
    ]


def test_roundtrips_a_day_whose_measurements_are_all_missing() -> None:
    """The last cycle of an export regularly has no scores yet; that is a
    real day with unknown values, not a reason to drop the row."""
    conn = init_db(":memory:")
    empty = RecoveryDay(date=DAY, cycle_start=datetime(2026, 7, 16, 1, 43, tzinfo=UTC))
    save_recovery_days(conn, [empty])

    loaded = load_recovery_days(conn)

    assert loaded == [empty]
    assert loaded[0].recovery_score is None
    assert loaded[0].hrv_ms is None


def test_stored_cycle_start_stays_timezone_aware_utc() -> None:
    """SQLite has no datetime type, so the timestamp goes through a string;
    it must come back aware, not naive."""
    conn = init_db(":memory:")
    save_recovery_days(conn, [_recovery_day()])

    loaded = load_recovery_days(conn)

    assert loaded[0].cycle_start == datetime(2026, 7, 16, 1, 43, tzinfo=UTC)


def test_save_raises_storage_error_on_a_broken_connection() -> None:
    conn = init_db(":memory:")
    conn.close()

    with pytest.raises(StorageError):
        save_recovery_days(conn, [_recovery_day()])


def test_load_raises_storage_error_on_a_broken_connection() -> None:
    conn = init_db(":memory:")
    conn.close()

    with pytest.raises(StorageError):
        load_recovery_days(conn)


def test_load_raises_storage_error_on_a_row_the_model_rejects() -> None:
    """A percentage of 150 cannot come from a valid import; if it is in the
    database, schema and model have drifted apart and that must surface."""
    conn = init_db(":memory:")
    conn.execute(
        "INSERT INTO recovery_days (date, cycle_start, recovery_score) "
        "VALUES (?, ?, ?)",
        (DAY.isoformat(), "2026-07-16T01:43:00+00:00", 150),
    )

    with pytest.raises(StorageError):
        load_recovery_days(conn)


def test_init_db_creates_the_recovery_table() -> None:
    conn = init_db(":memory:")

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert "recovery_days" in tables


def test_init_db_adds_the_recovery_table_to_an_existing_database(
    tmp_path: Path,
) -> None:
    """Every already-existing private database predates this table. Unlike a
    new column, a whole new table is covered by CREATE TABLE IF NOT EXISTS —
    this pins that down rather than assuming it."""
    db_path = tmp_path / "fitlytics.db"
    pre_existing = sqlite3.connect(db_path)
    pre_existing.execute(
        "CREATE TABLE workouts (id INTEGER PRIMARY KEY, start_time TEXT)"
    )
    pre_existing.execute(
        "INSERT INTO workouts (start_time) VALUES (?)", ("2026-07-16T14:00:00+00:00",)
    )
    pre_existing.commit()
    pre_existing.close()

    upgraded = init_db(db_path)
    save_recovery_days(upgraded, [_recovery_day()])

    assert load_recovery_days(upgraded) == [_recovery_day()]
    assert upgraded.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1
