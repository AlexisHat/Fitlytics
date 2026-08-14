"""Save and load the athlete's FTP/heart-rate profile to/from SQLite."""

import sqlite3

import deal

from errors import StorageError

_UPSERT_PROFILE = """
INSERT OR REPLACE INTO athlete_profile (id, ftp_watts, hr_rest, hr_max)
VALUES (1, ?, ?, ?)
"""

_SELECT_PROFILE = "SELECT ftp_watts, hr_rest, hr_max FROM athlete_profile WHERE id = 1"


@deal.raises(StorageError)
def save_profile(
    conn: sqlite3.Connection,
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> None:
    """Save the athlete's profile, replacing whatever was saved before.

    There is only ever one row: this is the athlete's current profile, not
    a history of edits to it.

    Args:
        conn: An open connection with the schema already created (see
            :func:`storage.schema.init_db`).
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Raises:
        StorageError: If the database write fails.
    """
    try:
        with conn:
            conn.execute(_UPSERT_PROFILE, (ftp_watts, hr_rest, hr_max))
    except sqlite3.Error as exc:
        raise StorageError(f"could not save athlete profile: {exc}") from exc


@deal.raises(StorageError)
def load_profile(
    conn: sqlite3.Connection,
) -> tuple[int | None, int | None, int | None]:
    """Load the athlete's saved profile.

    Args:
        conn: An open connection with the schema already created.

    Returns:
        ``(ftp_watts, hr_rest, hr_max)``, each None if never saved or saved
        as unknown; all None if nothing was saved yet at all.

    Raises:
        StorageError: If reading fails.
    """
    try:
        row = conn.execute(_SELECT_PROFILE).fetchone()
    except sqlite3.Error as exc:
        raise StorageError(f"could not load athlete profile: {exc}") from exc
    if row is None:
        return None, None, None
    return row["ftp_watts"], row["hr_rest"], row["hr_max"]
