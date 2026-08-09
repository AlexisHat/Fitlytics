"""Resampling of a workout's records onto a fixed-frequency time grid.

Interval detection needs a strictly regular time axis so later steps
(rolling windows, cumulative sums) don't have to special-case uneven sample
spacing. Real devices already record close to 1 Hz (see
``analysis.constants.PAUSE_GAP_THRESHOLD``), so this mostly turns "one row
per record" into "one row per second, with recording gaps left as explicit
nulls" rather than actually changing the sample rate.
"""

from itertools import pairwise
from typing import Final

import deal
import polars as pl

from models import RecordPoint

_RESAMPLED_COLUMNS: Final[tuple[str, ...]] = (
    "power",
    "heart_rate",
    "cadence",
    "speed_ms",
)
"""The record fields interval detection needs: power as the primary signal,
heart rate/cadence/speed as optional extras carried along for later
per-block reporting."""


@deal.pre(lambda records: len(records) > 0)
@deal.pre(lambda records: all(a.timestamp < b.timestamp for a, b in pairwise(records)))
@deal.ensure(
    lambda _: (
        len(_.result)
        == int((_.records[-1].timestamp - _.records[0].timestamp).total_seconds()) + 1
    )
)
def resample_to_1hz(records: list[RecordPoint]) -> pl.DataFrame:
    """Resample a workout's records onto a strict one-row-per-second grid.

    A gap in the recording (or, in principle, a device sampling slower than
    1 Hz) shows up as a row whose measurement columns are all null rather
    than as a missing row — later steps rely on this to recognise gaps
    without ever interpolating across them.

    Args:
        records: Records of a workout with strictly increasing timestamps;
            must not be empty. A real recording device never emits two
            samples for the same instant, so a duplicate or out-of-order
            timestamp is a caller error, not a state this function handles.

    Returns:
        A DataFrame with one row per whole second from the first to the
        last record's timestamp, columns ``timestamp``, ``power``,
        ``heart_rate``, ``cadence``, ``speed_ms``. A second with no
        matching record has null measurement values.

    Raises:
        deal.PreContractError: If ``records`` is empty or its timestamps
            are not strictly increasing.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start, power=100),
    ...     RecordPoint(timestamp=start + timedelta(seconds=3), power=120),
    ... ]
    >>> series = resample_to_1hz(records)
    >>> series["power"].to_list()
    [100, None, None, 120]
    """
    original = pl.DataFrame([record.model_dump() for record in records]).select(
        "timestamp", *_RESAMPLED_COLUMNS
    )
    grid = pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                records[0].timestamp,
                records[-1].timestamp,
                interval="1s",
                eager=True,
            )
        }
    )
    return grid.join(original, on="timestamp", how="left").sort("timestamp")
