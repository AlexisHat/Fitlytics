"""Save and load workouts to/from the local SQLite database."""

import sqlite3

import deal
from pydantic import ValidationError as PydanticValidationError

from errors import StorageError
from models import RecordPoint, Workout

_SELECT_WORKOUT_ID_BY_START_TIME = "SELECT id FROM workouts WHERE start_time = ?"

_INSERT_WORKOUT = """
INSERT INTO workouts (
    start_time, sport, sub_sport, ftp_watts, total_ascent_m, total_descent_m,
    avg_grade_pct, total_work_j, device_normalized_power,
    device_intensity_factor, device_training_stress_score
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_RECORD = """
INSERT INTO records (
    workout_id, timestamp, heart_rate, power, cadence, distance_m,
    speed_ms, altitude_m, grade_pct, latitude, longitude
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_ALL_WORKOUTS = """
SELECT id, start_time, sport, sub_sport, ftp_watts, total_ascent_m,
       total_descent_m, avg_grade_pct, total_work_j, device_normalized_power,
       device_intensity_factor, device_training_stress_score
FROM workouts
ORDER BY start_time
"""

_SELECT_RECORDS_FOR_WORKOUT = """
SELECT timestamp, heart_rate, power, cadence, distance_m, speed_ms,
       altitude_m, grade_pct, latitude, longitude
FROM records
WHERE workout_id = ?
ORDER BY timestamp
"""


@deal.raises(StorageError)
def save_workout(conn: sqlite3.Connection, workout: Workout) -> bool:
    """Save a workout and its records, skipping it if already saved.

    Args:
        conn: An open connection with the schema already created (see
            :func:`storage.schema.init_db`).
        workout: The workout to save.

    Returns:
        True if the workout was newly saved, False if a workout with the
        same start_time already existed and was left untouched.

    Raises:
        StorageError: If the database write fails.
    """
    try:
        existing = conn.execute(
            _SELECT_WORKOUT_ID_BY_START_TIME, (workout.start_time.isoformat(),)
        ).fetchone()
        if existing is not None:
            return False

        with conn:
            cursor = conn.execute(_INSERT_WORKOUT, _workout_row(workout))
            workout_id = cursor.lastrowid
            conn.executemany(
                _INSERT_RECORD,
                (_record_row(workout_id, record) for record in workout.records),
            )
        return True
    except sqlite3.Error as exc:
        raise StorageError(f"could not save workout: {exc}") from exc


def _workout_row(workout: Workout) -> tuple[object, ...]:
    """The column values for one INSERT INTO workouts, in table order."""
    return (
        workout.start_time.isoformat(),
        workout.sport,
        workout.sub_sport,
        workout.ftp_watts,
        workout.total_ascent_m,
        workout.total_descent_m,
        workout.avg_grade_pct,
        workout.total_work_j,
        workout.device_normalized_power,
        workout.device_intensity_factor,
        workout.device_training_stress_score,
    )


def _record_row(workout_id: int | None, record: RecordPoint) -> tuple[object, ...]:
    """The column values for one INSERT INTO records, in table order."""
    return (
        workout_id,
        record.timestamp.isoformat(),
        record.heart_rate,
        record.power,
        record.cadence,
        record.distance_m,
        record.speed_ms,
        record.altitude_m,
        record.grade_pct,
        record.latitude,
        record.longitude,
    )


def _record_from_row(row: sqlite3.Row) -> RecordPoint:
    return RecordPoint(
        timestamp=row["timestamp"],
        heart_rate=row["heart_rate"],
        power=row["power"],
        cadence=row["cadence"],
        distance_m=row["distance_m"],
        speed_ms=row["speed_ms"],
        altitude_m=row["altitude_m"],
        grade_pct=row["grade_pct"],
        latitude=row["latitude"],
        longitude=row["longitude"],
    )


def _workout_from_row(row: sqlite3.Row, records: list[RecordPoint]) -> Workout:
    return Workout(
        start_time=row["start_time"],
        sport=row["sport"],
        sub_sport=row["sub_sport"],
        ftp_watts=row["ftp_watts"],
        total_ascent_m=row["total_ascent_m"],
        total_descent_m=row["total_descent_m"],
        avg_grade_pct=row["avg_grade_pct"],
        total_work_j=row["total_work_j"],
        device_normalized_power=row["device_normalized_power"],
        device_intensity_factor=row["device_intensity_factor"],
        device_training_stress_score=row["device_training_stress_score"],
        records=records,
    )


@deal.raises(StorageError)
def load_workouts(conn: sqlite3.Connection) -> list[Workout]:
    """Load every saved workout, oldest first.

    Args:
        conn: An open connection with the schema already created.

    Returns:
        All saved workouts with their records, sorted by start_time.

    Raises:
        StorageError: If reading fails, or a stored row no longer forms a
            valid Workout/RecordPoint.
    """
    try:
        workouts = []
        for workout_row in conn.execute(_SELECT_ALL_WORKOUTS).fetchall():
            record_rows = conn.execute(
                _SELECT_RECORDS_FOR_WORKOUT, (workout_row["id"],)
            ).fetchall()
            records = [_record_from_row(row) for row in record_rows]
            workouts.append(_workout_from_row(workout_row, records))
        return workouts
    except (sqlite3.Error, PydanticValidationError) as exc:
        raise StorageError(f"could not load workouts: {exc}") from exc
