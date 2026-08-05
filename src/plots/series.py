"""Time-series preparation for a single workout's charts.

Converts a workout's records into a plotting-ready table with converted
units and a time-based rolling mean of power.
"""

from itertools import pairwise
from typing import Final

import deal
import polars as pl

from models import RecordPoint

_ROLLING_WINDOW: Final = "30s"
"""Trailing window for the smoothed power series, the same span Normalized
Power is defined over (see analysis.load.normalized_power) — computed
differently here, by elapsed time rather than sample count."""

_MEASUREMENT_COLUMNS: Final[tuple[str, ...]] = (
    "heart_rate",
    "power",
    "cadence",
    "speed_kmh",
    "altitude_m",
    "grade_pct",
    "distance_km",
)
"""Chart-relevant columns of the table :func:`build_time_series` returns."""


@deal.pre(lambda records: len(records) > 0)
@deal.pre(lambda records: all(a.timestamp <= b.timestamp for a, b in pairwise(records)))
@deal.ensure(lambda _: len(_.result) == len(_.records))
def build_time_series(records: list[RecordPoint]) -> pl.DataFrame:
    """Build a chart-ready time series from a workout's records.

    One row per record, in the same order. Units are converted once here:
    distance to kilometres, speed to km/h.

    Args:
        records: Time-ordered records of a workout; must not be empty.

    Returns:
        A DataFrame with columns ``timestamp``, ``elapsed_s`` (seconds
        since the first record), ``distance_km``, ``heart_rate``,
        ``power``, ``power_rolling_30s``, ``cadence``, ``speed_kmh``,
        ``altitude_m``, ``altitude_relative_m`` (altitude minus the first
        recorded altitude), ``grade_pct`` — one row per input record, in
        order.

    Raises:
        deal.PreContractError: If ``records`` is empty or not
            chronologically ordered.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start, power=100, heart_rate=140),
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=1), power=200, heart_rate=150
    ...     ),
    ... ]
    >>> series = build_time_series(records)
    >>> series["elapsed_s"].to_list()
    [0.0, 1.0]
    >>> series["power"].to_list()
    [100, 200]
    """
    series = pl.DataFrame([record.model_dump() for record in records])
    series = series.with_columns(
        (pl.col("timestamp") - pl.col("timestamp").first())
        .dt.total_milliseconds()
        .truediv(1000)
        .alias("elapsed_s"),
        pl.col("distance_m").cast(pl.Float64).truediv(1000).alias("distance_km"),
        pl.col("speed_ms").cast(pl.Float64).mul(3.6).alias("speed_kmh"),
        (pl.col("altitude_m") - pl.col("altitude_m").drop_nulls().first()).alias(
            "altitude_relative_m"
        ),
    )
    series = series.with_columns(
        pl.col("power")
        .cast(pl.Float64)
        .rolling_mean_by("timestamp", window_size=_ROLLING_WINDOW)
        .alias("power_rolling_30s")
    )
    return series.select(
        "timestamp",
        "elapsed_s",
        "distance_km",
        "heart_rate",
        "power",
        "power_rolling_30s",
        "cadence",
        "speed_kmh",
        "altitude_m",
        "altitude_relative_m",
        "grade_pct",
    )


def available_channels(series: pl.DataFrame) -> frozenset[str]:
    """Report which chart-relevant channels actually carry data.

    A channel the device never recorded (e.g. cadence with no cadence
    sensor fitted) is present in ``series`` as an all-null column rather
    than missing outright, so its presence in the table alone cannot
    answer "was this measured?" — every value has to be checked.

    Args:
        series: A time series built by :func:`build_time_series`.

    Returns:
        The subset of the chart-relevant columns with at least one
        non-null value.

    >>> from datetime import UTC, datetime
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, heart_rate=140)]
    >>> sorted(available_channels(build_time_series(records)))
    ['heart_rate']
    """
    return frozenset(
        column
        for column in _MEASUREMENT_COLUMNS
        if series[column].drop_nulls().len() > 0
    )
