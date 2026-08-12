"""SQLite schema and database initialization for local workout storage.

Two tables, mirroring ``Workout``/``RecordPoint`` field for field: ``workouts``
and, in a one-to-many relationship, their ``records``. Recovery days and
interval results are deliberately not persisted here — see
``docs/entscheidungen.md`` (Meilenstein 10).
"""

import sqlite3
from pathlib import Path

import deal

from errors import StorageError

_CREATE_WORKOUTS_TABLE = """
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL UNIQUE,
    sport TEXT NOT NULL,
    sub_sport TEXT,
    ftp_watts INTEGER,
    total_ascent_m REAL,
    total_descent_m REAL,
    avg_grade_pct REAL,
    total_work_j REAL,
    device_normalized_power INTEGER,
    device_intensity_factor REAL,
    device_training_stress_score REAL
)
"""
"""``start_time`` is UNIQUE (ISO 8601 UTC): the natural key for "is this
workout already saved?", since one athlete cannot start two workouts at the
exact same instant."""

_CREATE_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts(id),
    timestamp TEXT NOT NULL,
    heart_rate INTEGER,
    power INTEGER,
    cadence INTEGER,
    distance_m REAL,
    speed_ms REAL,
    altitude_m REAL,
    grade_pct REAL,
    latitude REAL,
    longitude REAL
)
"""


@deal.raises(StorageError)
def init_db(path: str | Path) -> sqlite3.Connection:
    """Open the local SQLite database, creating its schema if needed.

    Args:
        path: Filesystem path to the database file. The special string
            ``":memory:"`` opens a private, in-memory database instead
            (used by the test suite).

    Returns:
        An open connection with both tables present. Safe to call
        repeatedly on the same file — ``CREATE TABLE IF NOT EXISTS`` never
        touches data already there.

    Raises:
        StorageError: If the database file cannot be opened or the schema
            cannot be created.
    """
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute(_CREATE_WORKOUTS_TABLE)
            conn.execute(_CREATE_RECORDS_TABLE)
        return conn
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"could not initialize database: {exc}") from exc
