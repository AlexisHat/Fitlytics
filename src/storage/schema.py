"""SQLite schema and database initialization for local workout storage.

Three tables: ``workouts`` and, in a one-to-many relationship, their
``records``, mirroring ``Workout``/``RecordPoint`` field for field; and
``athlete_profile``, a single settings row for the FTP/heart-rate profile
entered in the sidebar. Recovery days and interval results are deliberately
not persisted here — see ``docs/entscheidungen.md`` (Meilenstein 10).
"""

import sqlite3
from pathlib import Path

import deal

from errors import StorageError

_CREATE_WORKOUTS_TABLE = """
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL UNIQUE,
    name TEXT,
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

_ADD_WORKOUTS_NAME_COLUMN = "ALTER TABLE workouts ADD COLUMN name TEXT"

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

_CREATE_ATHLETE_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS athlete_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ftp_watts INTEGER,
    hr_rest INTEGER,
    hr_max INTEGER
)
"""
"""``id`` is pinned to 1 by the CHECK constraint: this holds one athlete's
current profile, not a history of edits to it."""


def _ensure_workouts_name_column(conn: sqlite3.Connection) -> None:
    """Add ``workouts.name`` to a database created before this column existed.

    ``CREATE TABLE IF NOT EXISTS`` leaves an already-existing table
    untouched, so a database from before workout titles existed would
    otherwise never gain the new column.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(workouts)")}
    if "name" not in columns:
        conn.execute(_ADD_WORKOUTS_NAME_COLUMN)


@deal.raises(StorageError)
def init_db(path: str | Path) -> sqlite3.Connection:
    """Open the local SQLite database, creating its schema if needed.

    Args:
        path: Filesystem path to the database file. The special string
            ``":memory:"`` opens a private, in-memory database instead
            (used by the test suite).

    Returns:
        An open connection with all tables present and up to date. Safe to
        call repeatedly on the same file — ``CREATE TABLE IF NOT EXISTS``
        never touches data already there, and missing columns added by a
        later version are migrated in.

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
            conn.execute(_CREATE_ATHLETE_PROFILE_TABLE)
            _ensure_workouts_name_column(conn)
        return conn
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"could not initialize database: {exc}") from exc
