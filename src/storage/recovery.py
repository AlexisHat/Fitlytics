"""Save and load Whoop recovery days to/from the local SQLite database.

Unlike a workout, which is saved once and then never touched again, a
recovery day is *replaced* on re-import: a Whoop export always contains the
athlete's full history, and Whoop revises a score after the fact when it
gets more sleep data. The newer export therefore wins, keyed on the day
itself (see ``docs/entscheidungen.md``).
"""

import sqlite3
from datetime import date

import deal
from pydantic import ValidationError as PydanticValidationError

from errors import StorageError
from models import RecoveryDay

_UPSERT_RECOVERY_DAY = """
INSERT INTO recovery_days (
    date, cycle_start, recovery_score, resting_hr, hrv_ms, skin_temp_c,
    respiratory_rate, blood_oxygen
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    cycle_start = excluded.cycle_start,
    recovery_score = excluded.recovery_score,
    resting_hr = excluded.resting_hr,
    hrv_ms = excluded.hrv_ms,
    skin_temp_c = excluded.skin_temp_c,
    respiratory_rate = excluded.respiratory_rate,
    blood_oxygen = excluded.blood_oxygen
"""

_SELECT_ALL_RECOVERY_DAYS = """
SELECT date, cycle_start, recovery_score, resting_hr, hrv_ms, skin_temp_c,
       respiratory_rate, blood_oxygen
FROM recovery_days
ORDER BY date
"""


def _recovery_row(day: RecoveryDay) -> tuple[object, ...]:
    """The column values for one recovery_days upsert, in table order."""
    return (
        day.date.isoformat(),
        day.cycle_start.isoformat(),
        day.recovery_score,
        day.resting_hr,
        day.hrv_ms,
        day.skin_temp_c,
        day.respiratory_rate,
        day.blood_oxygen,
    )


def _recovery_day_from_row(row: sqlite3.Row) -> RecoveryDay:
    """Rebuild a RecoveryDay from one stored row."""
    return RecoveryDay(
        date=date.fromisoformat(row["date"]),
        cycle_start=row["cycle_start"],
        recovery_score=row["recovery_score"],
        resting_hr=row["resting_hr"],
        hrv_ms=row["hrv_ms"],
        skin_temp_c=row["skin_temp_c"],
        respiratory_rate=row["respiratory_rate"],
        blood_oxygen=row["blood_oxygen"],
    )


@deal.raises(StorageError)
@deal.ensure(lambda _: _.result >= 0)
def save_recovery_days(conn: sqlite3.Connection, days: list[RecoveryDay]) -> int:
    """Save recovery days, replacing any already stored for the same date.

    Args:
        conn: An open connection with the schema already created (see
            :func:`storage.schema.init_db`).
        days: The recovery days to save. May be empty, which saves nothing.

    Returns:
        How many days were written.

    Raises:
        StorageError: If the database write fails.
    """
    try:
        with conn:
            conn.executemany(_UPSERT_RECOVERY_DAY, [_recovery_row(day) for day in days])
        return len(days)
    except sqlite3.Error as exc:
        raise StorageError(f"could not save recovery days: {exc}") from exc


@deal.raises(StorageError)
def load_recovery_days(conn: sqlite3.Connection) -> list[RecoveryDay]:
    """Load every stored recovery day, oldest first.

    Args:
        conn: An open connection with the schema already created (see
            :func:`storage.schema.init_db`).

    Returns:
        Every stored recovery day, sorted by date.

    Raises:
        StorageError: If the database read fails, or a stored row can no
            longer be validated against the current model — a schema and
            model that have drifted apart is a defect to surface, not to
            paper over by skipping the row.
    """
    try:
        rows = conn.execute(_SELECT_ALL_RECOVERY_DAYS).fetchall()
        return [_recovery_day_from_row(row) for row in rows]
    except sqlite3.Error as exc:
        raise StorageError(f"could not load recovery days: {exc}") from exc
    except PydanticValidationError as exc:
        raise StorageError(f"stored recovery day is not valid: {exc}") from exc
