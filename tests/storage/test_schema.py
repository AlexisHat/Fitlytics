"""Tests for storage.schema."""

import sqlite3
from pathlib import Path

import pytest

from errors import StorageError
from storage.schema import init_db


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def test_init_db_creates_all_tables() -> None:
    conn = init_db(":memory:")

    assert {"workouts", "records", "athlete_profile"}.issubset(_table_names(conn))


def test_init_db_is_idempotent_and_keeps_existing_data(tmp_path: Path) -> None:
    db_path = tmp_path / "fitlytics.db"

    first = init_db(db_path)
    first.execute(
        "INSERT INTO workouts (start_time, sport) VALUES (?, ?)",
        ("2026-07-16T14:00:00+00:00", "cycling"),
    )
    first.commit()
    first.close()

    second = init_db(db_path)
    rows = second.execute("SELECT sport FROM workouts").fetchall()
    second.close()

    assert [row["sport"] for row in rows] == ["cycling"]


def test_init_db_rejects_an_unopenable_path(tmp_path: Path) -> None:
    unwritable_path = tmp_path / "does-not-exist" / "fitlytics.db"

    with pytest.raises(StorageError):
        init_db(unwritable_path)


def test_init_db_migrates_a_workouts_table_from_before_names_existed(
    tmp_path: Path,
) -> None:
    """A database from before workout titles existed has no ``name`` column
    yet — CREATE TABLE IF NOT EXISTS alone would never add it."""
    db_path = tmp_path / "fitlytics.db"

    pre_existing = sqlite3.connect(db_path)
    pre_existing.execute(
        """
        CREATE TABLE workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL UNIQUE,
            sport TEXT NOT NULL
        )
        """
    )
    pre_existing.execute(
        "INSERT INTO workouts (start_time, sport) VALUES (?, ?)",
        ("2026-07-16T14:00:00+00:00", "cycling"),
    )
    pre_existing.commit()
    pre_existing.close()

    migrated = init_db(db_path)
    rows = migrated.execute("SELECT sport, name FROM workouts").fetchall()

    assert [(row["sport"], row["name"]) for row in rows] == [("cycling", None)]
