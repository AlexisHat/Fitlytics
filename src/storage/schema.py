"""SQLite schema and database initialization for local workout storage.

Four tables: ``workouts`` and, in a one-to-many relationship, their
``records``, mirroring ``Workout``/``RecordPoint`` field for field;
``recovery_days``, one row per Whoop cycle; and ``athlete_profile``, a
single settings row for the FTP/heart-rate profile entered in the sidebar.
Interval results are deliberately not persisted — they are derived from the
records and recomputed on demand, see ``docs/entscheidungen.md``.
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
    category TEXT,
    sport TEXT NOT NULL,
    sub_sport TEXT,
    ftp_watts INTEGER,
    total_ascent_m REAL,
    total_descent_m REAL,
    avg_grade_pct REAL,
    total_work_j REAL,
    device_normalized_power INTEGER,
    device_intensity_factor REAL,
    device_training_stress_score REAL,
    planned_interval_repetitions INTEGER,
    planned_interval_duration_s INTEGER,
    planned_interval_target_power_w INTEGER
)
"""
"""``start_time`` is UNIQUE (ISO 8601 UTC): the natural key for "is this
workout already saved?", since one athlete cannot start two workouts at the
exact same instant."""

_WORKOUTS_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("name", "ALTER TABLE workouts ADD COLUMN name TEXT"),
    ("category", "ALTER TABLE workouts ADD COLUMN category TEXT"),
    (
        "planned_interval_repetitions",
        "ALTER TABLE workouts ADD COLUMN planned_interval_repetitions INTEGER",
    ),
    (
        "planned_interval_duration_s",
        "ALTER TABLE workouts ADD COLUMN planned_interval_duration_s INTEGER",
    ),
    (
        "planned_interval_target_power_w",
        "ALTER TABLE workouts ADD COLUMN planned_interval_target_power_w INTEGER",
    ),
)
"""Columns introduced after ``workouts`` was first created, each with the
``ALTER TABLE`` statement that adds it to a database missing it."""

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

_CREATE_RECOVERY_DAYS_TABLE = """
CREATE TABLE IF NOT EXISTS recovery_days (
    date TEXT PRIMARY KEY,
    cycle_start TEXT NOT NULL,
    recovery_score INTEGER,
    resting_hr INTEGER,
    hrv_ms REAL,
    skin_temp_c REAL,
    respiratory_rate REAL,
    blood_oxygen REAL
)
"""
"""``date`` (local calendar day, ISO 8601) is the primary key rather than a
surrogate id: Whoop reports exactly one cycle per day, and an export always
contains the full history, so re-importing must update a day rather than
append a second copy of it."""

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


def _ensure_workouts_columns(conn: sqlite3.Connection) -> None:
    """Add any ``workouts`` columns missing on a database from an older version.

    ``CREATE TABLE IF NOT EXISTS`` leaves an already-existing table
    untouched, so a database created before a given column existed would
    otherwise never gain it.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(workouts)")}
    for column, statement in _WORKOUTS_COLUMN_MIGRATIONS:
        if column not in existing:
            conn.execute(statement)


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
            conn.execute(_CREATE_RECOVERY_DAYS_TABLE)
            conn.execute(_CREATE_ATHLETE_PROFILE_TABLE)
            _ensure_workouts_columns(conn)
        return conn
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"could not initialize database: {exc}") from exc
