"""Import recovery metrics from a Whoop physiological-cycles CSV export."""

from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from typing import IO, Any, Final

import deal
import polars as pl
from pydantic import ValidationError as PydanticValidationError

from errors import FileImportError
from models import RecoveryDay

_CYCLE_DAY_SHIFT: Final = timedelta(hours=12)
"""Offset that maps a cycle to the day it reports on (noon-to-noon)."""


def _parse_utc_offset(zone: str) -> timezone:
    """Parse a Whoop timezone string into a fixed UTC offset.

    Args:
        zone: Timezone as exported by Whoop, e.g. ``"UTC+02:00"``, or the
            zero-offset spelling ``"UTCZ"``.

    Returns:
        The corresponding fixed-offset timezone.

    Raises:
        ValueError: If ``zone`` does not match either format.

    >>> _parse_utc_offset("UTCZ")
    datetime.timezone.utc
    >>> _parse_utc_offset("UTC+02:00")
    datetime.timezone(datetime.timedelta(seconds=7200))
    >>> _parse_utc_offset("UTC-05:00")
    datetime.timezone(datetime.timedelta(days=-1, seconds=68400))
    """
    if zone == "UTCZ":
        return UTC
    sign = 1 if zone[3] == "+" else -1
    hours, minutes = zone[4:].split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def _build_recovery_day(row: dict[str, Any]) -> RecoveryDay:
    """Build a RecoveryDay from a Whoop CSV row.

    The row's start time is local, with the UTC offset given separately
    (e.g. ``"2026-07-23 01:43:25"`` + ``"UTC+02:00"``). ``cycle_start`` is
    that instant in UTC, which can fall on the previous day.

    A Whoop cycle spans one sleep plus the waking day after it, so it is not
    a calendar day: going to bed before midnight starts the cycle that
    reports on the next day. Taking the start date verbatim would label
    such a cycle a day too early and collide with the cycle that began after
    midnight of the same date. ``date`` therefore uses a noon-to-noon
    convention — the day in which the cycle's midpoint falls — which leaves
    the usual after-midnight bedtime untouched and keeps one entry per day.

    Args:
        row: A single row of ``physiologische_zyklen.csv``, keyed by
            column name.

    Returns:
        The corresponding RecoveryDay.

    Raises:
        KeyError: If a required column is missing.
        ValueError: If the start time or timezone cannot be parsed.
        pydantic.ValidationError: If a present field has an unusable value.

    >>> row = {
    ...     "Startzeit des Zyklus": "2026-07-23 01:43:25",
    ...     "Zeitzone des Zyklus": "UTC+02:00",
    ...     "Erholungswert %": 73,
    ... }
    >>> day = _build_recovery_day(row)
    >>> day.date
    datetime.date(2026, 7, 23)
    >>> day.cycle_start
    datetime.datetime(2026, 7, 22, 23, 43, 25, tzinfo=datetime.timezone.utc)
    >>> day.recovery_score
    73

    A cycle begun in the evening reports on the following day:

    >>> evening = {
    ...     "Startzeit des Zyklus": "2026-03-27 22:06:55",
    ...     "Zeitzone des Zyklus": "UTC+01:00",
    ... }
    >>> _build_recovery_day(evening).date
    datetime.date(2026, 3, 28)
    """
    local_time = datetime.strptime(row["Startzeit des Zyklus"], "%Y-%m-%d %H:%M:%S")
    offset = _parse_utc_offset(row["Zeitzone des Zyklus"])

    return RecoveryDay(
        date=(local_time + _CYCLE_DAY_SHIFT).date(),
        cycle_start=local_time.replace(tzinfo=offset),
        recovery_score=row.get("Erholungswert %"),
        resting_hr=row.get("Ruheherzfrequenz (Schläge pro Minute)"),
        hrv_ms=row.get("Herzfrequenzvariabilität (ms)"),
        skin_temp_c=row.get("Hauttemperatur (Celsius)"),
        respiratory_rate=row.get("Atemfrequenz (Atemzüge/Min.)"),
        blood_oxygen=row.get("Blutsauerstoff %"),
    )


@deal.raises(FileImportError)
@deal.post(lambda result: len(result) >= 1)
@deal.post(
    lambda result: all(a.cycle_start <= b.cycle_start for a, b in pairwise(result))
)
def import_whoop_csv(source: str | Path | IO[bytes]) -> list[RecoveryDay]:
    """Import daily recovery metrics from a Whoop CSV export.

    Args:
        source: A filesystem path, or a file-like object such as
            Streamlit's ``UploadedFile`` returned by ``st.file_uploader()``.

    Returns:
        The recovery days, sorted chronologically (earliest first) —
        Whoop's own export order is newest-first.

    Raises:
        FileImportError: If the file cannot be read, is not a valid CSV,
            contains no data rows, or has unusable row data.
    """
    try:
        rows = list(pl.read_csv(source).iter_rows(named=True))

        if not rows:
            raise FileImportError("CSV file contains no data rows")

        days = [_build_recovery_day(row) for row in rows]
        days.sort(key=lambda day: day.cycle_start)
        return days
    except (
        pl.exceptions.PolarsError,
        OSError,
        KeyError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise FileImportError(f"could not import Whoop CSV file: {exc}") from exc
