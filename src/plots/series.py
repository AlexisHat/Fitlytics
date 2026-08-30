"""Time-series preparation for a single workout's charts.

Converts a workout's records into a plotting-ready table with converted
units, a time-based rolling mean of power and a rolling median of altitude.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from typing import Final

import deal
import polars as pl

from models import RecordPoint

_ROLLING_WINDOW: Final = "30s"
"""Trailing window for the smoothed power series, the same span Normalized
Power is defined over (see analysis.load.normalized_power) — computed
differently here, by elapsed time rather than sample count."""

_ALTITUDE_SMOOTHING_WINDOW: Final = "15s"
"""Trailing window for the rolling median damping barometer/GPS noise out
of the elevation profile. A median rather than a mean, so a single spurious
reading is dropped outright rather than dragging the curve toward it. The
same window is used for :func:`elevation_gain_m`, so the displayed profile
and any ascent computed from it can never disagree with each other."""

_ELAPSED_AXIS_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
"""Arbitrary anchor for formatting elapsed_s as a clock string; only the
time-of-day part is ever read back out (via ``%H:%M:%S``), so any date
works as the anchor."""

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
        since the first record), ``elapsed_hms`` (the same, formatted as
        ``HH:MM:SS``), ``distance_km``, ``heart_rate``, ``power``,
        ``power_rolling_30s``, ``cadence``, ``speed_kmh``, ``altitude_m``,
        ``altitude_smoothed_m`` (rolling median, see
        :data:`_ALTITUDE_SMOOTHING_WINDOW`), ``grade_pct``, ``latitude``,
        ``longitude`` — one row per input record, in order.

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
    # infer_schema_length=None scans every row instead of just the first 100
    # (polars' default) before picking each column's dtype — otherwise a
    # column that is None in the first 100 records but a real float later
    # (e.g. grade_pct before the first gradient reading) crashes with
    # "could not append value ... to the builder" on a long enough ride.
    series = pl.DataFrame(
        [record.model_dump() for record in records], infer_schema_length=None
    )
    series = series.with_columns(
        (pl.col("timestamp") - pl.col("timestamp").first())
        .dt.total_milliseconds()
        .truediv(1000)
        .alias("elapsed_s"),
        pl.col("distance_m").cast(pl.Float64).truediv(1000).alias("distance_km"),
        pl.col("speed_ms").cast(pl.Float64).mul(3.6).alias("speed_kmh"),
    )
    series = series.with_columns(
        pl.col("power")
        .cast(pl.Float64)
        .rolling_mean_by("timestamp", window_size=_ROLLING_WINDOW)
        .alias("power_rolling_30s"),
        pl.col("altitude_m")
        .cast(pl.Float64)
        .rolling_median_by("timestamp", window_size=_ALTITUDE_SMOOTHING_WINDOW)
        .alias("altitude_smoothed_m"),
        (pl.lit(_ELAPSED_AXIS_EPOCH) + pl.duration(seconds=pl.col("elapsed_s")))
        .dt.strftime("%H:%M:%S")
        .alias("elapsed_hms"),
    )
    return series.select(
        "timestamp",
        "elapsed_s",
        "elapsed_hms",
        "distance_km",
        "heart_rate",
        "power",
        "power_rolling_30s",
        "cadence",
        "speed_kmh",
        "altitude_m",
        "altitude_smoothed_m",
        "grade_pct",
        "latitude",
        "longitude",
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


def trim_to_first_fully_measured_row(
    series: pl.DataFrame, required_columns: Sequence[str]
) -> pl.DataFrame:
    """Drop leading rows until every required column has a value.

    A GPS or barometric sensor can take seconds to minutes to acquire a
    signal, well after sensors like a heart-rate strap or power meter are
    already reporting — showing that gap as a staggered start makes a chart
    look misaligned rather than simply incomplete. Used both for a
    timeline's shown panels and, first, for the distance axis itself (see
    :mod:`plots.distance`) that every panel now depends on.

    Args:
        series: A time series built by :func:`build_time_series`.
        required_columns: Columns that must all be non-null on the same row.

    Returns:
        ``series`` from its first fully-measured row onward, with
        ``elapsed_s`` re-based to start at zero there. Unchanged if the
        required columns are never all measured on the same row.

    >>> series = pl.DataFrame(
    ...     {
    ...         "elapsed_s": [0.0, 1.0, 2.0],
    ...         "power": [100, 110, 120],
    ...         "altitude_smoothed_m": [None, None, 5.0],
    ...     }
    ... )
    >>> trimmed = trim_to_first_fully_measured_row(
    ...     series, ["power", "altitude_smoothed_m"]
    ... )
    >>> trimmed["elapsed_s"].to_list()
    [0.0]
    >>> trimmed["power"].to_list()
    [120]
    """
    mask = pl.all_horizontal([pl.col(c).is_not_null() for c in required_columns])
    live_rows = series.with_row_index().filter(mask)
    if live_rows.is_empty():
        return series

    trimmed = series.slice(live_rows["index"][0])
    offset = trimmed["elapsed_s"][0]
    return trimmed.with_columns((pl.col("elapsed_s") - offset).alias("elapsed_s"))


def elevation_gain_m(altitudes: Sequence[float | None]) -> float | None:
    """Sum the positive deltas of an altitude series into a total ascent.

    Meant to run on the same smoothed altitude the elevation panel and its
    navigator draw (:attr:`~plots.series` column ``altitude_smoothed_m``),
    so a self-computed ascent figure can never disagree with the profile
    shown next to it. Not wired into
    :attr:`analysis.workout.WorkoutMetrics.elevation_gain_m`, which
    deliberately keeps trusting the device's own figure — see
    ``docs/entscheidungen.md``.

    Args:
        altitudes: An altitude reading per record, in metres, in order;
            ``None`` where unmeasured. Null readings are skipped rather
            than treated as a drop to zero.

    Returns:
        The total climbed metres, or None if fewer than two readings are
        available to form a delta from.

    >>> elevation_gain_m([100.0, 105.0, 102.0, 110.0])
    13.0
    >>> elevation_gain_m([100.0, None, 110.0])
    10.0
    >>> elevation_gain_m([100.0]) is None
    True
    """
    values = [altitude for altitude in altitudes if altitude is not None]
    if len(values) < 2:
        return None
    return sum(max(0.0, later - earlier) for earlier, later in pairwise(values))
