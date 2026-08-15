"""Turning a workout's records into a clean signal for interval detection.

Interval detection needs a strictly regular time axis so later steps
(rolling windows, cumulative sums) don't have to special-case uneven sample
spacing. Real devices already record close to 1 Hz (see
``analysis.constants.PAUSE_GAP_THRESHOLD``), so resampling mostly turns "one
row per record" into "one row per second, with recording gaps left as
explicit nulls" rather than actually changing the sample rate. On top of
that grid, standstill detection marks stretches where the rider stopped
(e.g. a red light) while the device kept recording — a different kind of
hard block boundary than a recording gap — and a rolling quantile estimates
the ride's local baseline power that later steps compare against.
"""

from datetime import timedelta
from itertools import groupby, pairwise
from typing import Final

import deal
import polars as pl

from intervals.config import (
    BASELINE_QUANTILE,
    BASELINE_WINDOW_S,
    STANDSTILL_MIN_DURATION,
    STANDSTILL_POWER_THRESHOLD_W,
    STANDSTILL_SPEED_THRESHOLD_MS,
)
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
    # infer_schema_length=None scans every row instead of just the first 100
    # (polars' default) before picking each column's dtype — otherwise a
    # column that is None in the first 100 records but a real float later
    # (e.g. grade_pct before the first gradient reading) crashes with
    # "could not append value ... to the builder" on a long enough ride.
    original = pl.DataFrame(
        [record.model_dump() for record in records], infer_schema_length=None
    ).select("timestamp", *_RESAMPLED_COLUMNS)
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


def _run_lengths(flags: list[bool]) -> list[int]:
    """Lengths of the maximal True-runs in a boolean sequence.

    >>> _run_lengths([False, True, True, False, True])
    [2, 1]
    """
    return [len(list(group)) for value, group in groupby(flags) if value]


def is_1hz_spaced(series: pl.DataFrame) -> bool:
    """Whether every row of ``series`` is exactly one second after the last.

    >>> import polars as pl
    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> stamps = pl.Series([start, start + timedelta(seconds=1)])
    >>> is_1hz_spaced(pl.DataFrame({"timestamp": stamps}))
    True
    >>> stamps = pl.Series([start, start + timedelta(seconds=2)])
    >>> is_1hz_spaced(pl.DataFrame({"timestamp": stamps}))
    False
    """
    gaps = series["timestamp"].diff().drop_nulls()
    return bool((gaps == timedelta(seconds=1)).all())


@deal.pre(lambda series: len(series) > 0)
@deal.pre(lambda series: is_1hz_spaced(series))
@deal.ensure(
    lambda _: all(
        length >= STANDSTILL_MIN_DURATION.total_seconds()
        for length in _run_lengths(_.result["is_standstill"].to_list())
    )
)
def mark_standstill(series: pl.DataFrame) -> pl.DataFrame:
    """Mark rows where the rider stood still while recording kept running.

    Distinct from a recording gap (see :func:`resample_to_1hz`): here the
    device keeps sampling throughout, e.g. waiting at a red light, whereas a
    gap means recording itself stopped. Both are, deliberately, hard block
    boundaries for interval detection — just for different reasons.

    Args:
        series: A 1 Hz-gridded time series, as returned by
            :func:`resample_to_1hz`; must not be empty.

    Returns:
        ``series`` with an added boolean ``is_standstill`` column, True for
        every row in a contiguous near-zero-power stretch of at least
        ``STANDSTILL_MIN_DURATION``. If any speed was recorded at all,
        speed must also be near zero throughout the stretch; a workout with
        no speed data at all (e.g. an indoor trainer without a speed
        sensor) is judged on power alone. A row with no power reading (a
        gap, or a workout with no power meter at all) is never marked as
        standstill.

    Raises:
        deal.PreContractError: If ``series`` is empty or not spaced exactly
            one second apart.

    >>> from datetime import UTC, datetime
    >>> records = [
    ...     RecordPoint(timestamp=datetime(2026, 7, 16, 14, 0, i, tzinfo=UTC), power=p)
    ...     for i, p in enumerate([200] * 5 + [0] * 25 + [200] * 5)
    ... ]
    >>> series = mark_standstill(resample_to_1hz(records))
    >>> series["is_standstill"].to_list()[:5]
    [False, False, False, False, False]
    >>> all(series["is_standstill"].to_list()[5:30])
    True
    >>> series["is_standstill"].to_list()[30:]
    [False, False, False, False, False]
    """
    has_speed = series["speed_ms"].drop_nulls().len() > 0

    near_zero = pl.col("power").is_not_null() & (
        pl.col("power") <= STANDSTILL_POWER_THRESHOLD_W
    )
    if has_speed:
        near_zero = (
            near_zero
            & pl.col("speed_ms").is_not_null()
            & (pl.col("speed_ms") <= STANDSTILL_SPEED_THRESHOLD_MS)
        )

    with_runs = series.with_columns(near_zero.alias("_near_zero")).with_columns(
        (pl.col("_near_zero") != pl.col("_near_zero").shift(1, fill_value=False))
        .cum_sum()
        .alias("_run_id")
    )
    run_lengths = with_runs.group_by("_run_id").agg(pl.len().alias("_run_length"))
    return (
        with_runs.join(run_lengths, on="_run_id", how="left")
        .with_columns(
            (
                pl.col("_near_zero")
                & (pl.col("_run_length") >= STANDSTILL_MIN_DURATION.total_seconds())
            ).alias("is_standstill")
        )
        .drop("_near_zero", "_run_id", "_run_length")
    )


@deal.pre(lambda series: len(series) > 0)
@deal.pre(lambda series: is_1hz_spaced(series))
@deal.ensure(
    lambda _: (
        _.series["power"].min() is None
        or _.result["baseline_power"]
        .drop_nulls()
        .is_between(_.series["power"].min(), _.series["power"].max())
        .all()
    )
)
def compute_baseline(series: pl.DataFrame) -> pl.DataFrame:
    """Estimate a ride's local baseline power with a centred rolling quantile.

    A long window (``BASELINE_WINDOW_S``, a ten-minute default) smooths over
    individual interval repetitions while still tracking a ride whose base
    intensity drifts over its duration — a warm-up followed by a climb has a
    different baseline for each part, which a single global median would
    blur together. A low quantile (``BASELINE_QUANTILE``) rather than the
    median: a repeated-interval session can spend more than half of any
    600 s window actually working, so the median would often sit at or near
    the block's own power instead of the recovery level baseline is meant
    to represent. The window shrinks at both ends of the ride rather than
    padding with invented values, so the first and last seconds still get a
    baseline computed from the samples actually available there.

    Args:
        series: A 1 Hz-gridded time series, as returned by
            :func:`resample_to_1hz`; must not be empty.

    Returns:
        ``series`` with an added ``baseline_power`` column: the centred
        rolling ``BASELINE_QUANTILE`` of ``power``, in watts. Null power
        readings (a gap, or no power meter at all) are skipped rather than
        treated as zero; a second with no non-null power within its window
        is null.

    Raises:
        deal.PreContractError: If ``series`` is empty or not spaced exactly
            one second apart.

    >>> from datetime import UTC, datetime
    >>> records = [
    ...     RecordPoint(timestamp=datetime(2026, 7, 16, 14, 0, i, tzinfo=UTC), power=p)
    ...     for i, p in enumerate([100, 100, 100, 400, 100, 100, 100])
    ... ]
    >>> series = compute_baseline(resample_to_1hz(records))
    >>> series["baseline_power"].to_list()
    [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    """
    return series.with_columns(
        pl.col("power")
        .cast(pl.Float64)
        .rolling_quantile(
            BASELINE_QUANTILE, window_size=BASELINE_WINDOW_S, center=True, min_samples=1
        )
        .alias("baseline_power")
    )
