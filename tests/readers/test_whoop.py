"""Tests for readers.whoop."""

import io
from datetime import UTC, date, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

import pytest

from errors import FileImportError
from readers.whoop import _build_recovery_day, _parse_utc_offset, import_whoop_csv

VALID_FIXTURE = Path("data/beispiel/fixtures/physiologische_zyklen_gueltig.csv")
EMPTY_FIXTURE = Path("data/beispiel/fixtures/physiologische_zyklen_leer.csv")
BROKEN_FIXTURE = Path("data/beispiel/fixtures/physiologische_zyklen_defekt.csv")


def test_import_whoop_csv_reads_valid_fixture() -> None:
    days = import_whoop_csv(VALID_FIXTURE)

    assert len(days) == 10
    assert days[0].date == date(2025, 8, 15)
    assert days[0].recovery_score is None
    assert days[-1].date == date(2026, 7, 23)
    assert days[-1].cycle_start == datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC)
    assert days[-1].recovery_score == 73


def test_import_whoop_csv_is_sorted_ascending() -> None:
    days = import_whoop_csv(VALID_FIXTURE)

    assert all(a.cycle_start <= b.cycle_start for a, b in pairwise(days))


def test_import_whoop_csv_accepts_file_like_object() -> None:
    with VALID_FIXTURE.open("rb") as fh:
        days = import_whoop_csv(fh)

    assert len(days) == 10


def test_import_whoop_csv_accepts_bytes_buffer() -> None:
    buffer = io.BytesIO(VALID_FIXTURE.read_bytes())

    days = import_whoop_csv(buffer)

    assert len(days) == 10


def test_import_whoop_csv_rejects_missing_path() -> None:
    with pytest.raises(FileImportError):
        import_whoop_csv(Path("data/beispiel/fixtures/does_not_exist.csv"))


def test_import_whoop_csv_rejects_broken_file() -> None:
    with pytest.raises(FileImportError):
        import_whoop_csv(BROKEN_FIXTURE)


def test_import_whoop_csv_rejects_empty_file() -> None:
    with pytest.raises(FileImportError):
        import_whoop_csv(EMPTY_FIXTURE)


def test_parse_utc_offset_handles_zulu_spelling() -> None:
    assert _parse_utc_offset("UTCZ") == UTC


def test_parse_utc_offset_handles_negative_offset() -> None:
    assert _parse_utc_offset("UTC-05:00") == timezone(timedelta(hours=-5))


def test_build_recovery_day_converts_cycle_start_to_utc() -> None:
    row = {
        "Startzeit des Zyklus": "2026-07-23 01:43:25",
        "Zeitzone des Zyklus": "UTC+02:00",
    }

    day = _build_recovery_day(row)

    assert day.date == date(2026, 7, 23)
    assert day.cycle_start == datetime(2026, 7, 22, 23, 43, 25, tzinfo=UTC)


def test_build_recovery_day_dates_an_after_midnight_cycle_to_that_same_day() -> None:
    row = {
        "Startzeit des Zyklus": "2026-07-23 03:12:00",
        "Zeitzone des Zyklus": "UTC+02:00",
    }

    assert _build_recovery_day(row).date == date(2026, 7, 23)


def test_build_recovery_day_dates_an_evening_cycle_to_the_following_day() -> None:
    """A cycle begun before midnight reports on the day one wakes up in."""
    row = {
        "Startzeit des Zyklus": "2026-03-27 22:06:55",
        "Zeitzone des Zyklus": "UTC+01:00",
    }

    assert _build_recovery_day(row).date == date(2026, 3, 28)


def test_import_whoop_csv_gives_each_day_a_distinct_date() -> None:
    """The noon-to-noon rule is what makes the date unique per cycle."""
    days = import_whoop_csv(VALID_FIXTURE)

    dates = [day.date for day in days]
    assert len(set(dates)) == len(dates)


def test_build_recovery_day_maps_optional_fields_to_none_when_absent() -> None:
    row = {"Startzeit des Zyklus": "2026-07-23 01:43:25", "Zeitzone des Zyklus": "UTCZ"}

    day = _build_recovery_day(row)

    assert day.recovery_score is None
    assert day.hrv_ms is None


def test_build_recovery_day_raises_without_start_time() -> None:
    with pytest.raises(KeyError):
        _build_recovery_day({"Zeitzone des Zyklus": "UTCZ"})
