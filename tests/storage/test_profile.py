"""Tests for storage.profile."""

import sqlite3

import pytest

from errors import StorageError
from storage.profile import load_profile, save_profile
from storage.schema import init_db


@pytest.fixture
def conn() -> sqlite3.Connection:
    return init_db(":memory:")


def test_load_profile_returns_all_none_when_nothing_was_saved(
    conn: sqlite3.Connection,
) -> None:
    assert load_profile(conn) == (None, None, None)


def test_save_and_load_profile_roundtrips_all_fields(conn: sqlite3.Connection) -> None:
    save_profile(conn, ftp_watts=210, hr_rest=50, hr_max=190)

    assert load_profile(conn) == (210, 50, 190)


def test_save_profile_roundtrips_partial_fields(conn: sqlite3.Connection) -> None:
    save_profile(conn, ftp_watts=210, hr_rest=None, hr_max=None)

    assert load_profile(conn) == (210, None, None)


def test_save_profile_overwrites_the_previous_save(conn: sqlite3.Connection) -> None:
    save_profile(conn, ftp_watts=210, hr_rest=50, hr_max=190)
    save_profile(conn, ftp_watts=220, hr_rest=48, hr_max=188)

    assert load_profile(conn) == (220, 48, 188)


def test_save_profile_keeps_only_a_single_row(conn: sqlite3.Connection) -> None:
    save_profile(conn, ftp_watts=210, hr_rest=50, hr_max=190)
    save_profile(conn, ftp_watts=220, hr_rest=48, hr_max=188)

    rows = conn.execute("SELECT COUNT(*) AS n FROM athlete_profile").fetchone()
    assert rows["n"] == 1


def test_save_profile_wraps_a_closed_connection_as_storage_error() -> None:
    closed_conn = init_db(":memory:")
    closed_conn.close()

    with pytest.raises(StorageError):
        save_profile(closed_conn, ftp_watts=210, hr_rest=50, hr_max=190)


def test_load_profile_wraps_a_closed_connection_as_storage_error() -> None:
    closed_conn = init_db(":memory:")
    closed_conn.close()

    with pytest.raises(StorageError):
        load_profile(closed_conn)
