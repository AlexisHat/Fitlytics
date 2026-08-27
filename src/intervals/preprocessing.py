"""Turning a workout's records into a clean signal for interval detection.

Interval detection needs a strictly regular time axis so later steps
(rolling windows, cumulative sums) don't have to special-case uneven sample
spacing. Real devices already record close to 1 Hz (see
``analysis.constants.PAUSE_GAP_THRESHOLD``), so resampling mostly turns "one
row per record" into "one row per second, with recording gaps left as
explicit nulls" rather than actually changing the sample rate. On top of
that grid, standstill detection marks stretches where the rider stopped
(e.g. a red light) while the device kept recording — a different kind of
hard block boundary than a recording gap.

Detection itself works on a smoothed copy of the power signal rather than
the raw one, measured against a threshold derived from the ride's own power
distribution; see :func:`smooth_power` and :func:`effort_threshold`.
"""

from datetime import timedelta
from itertools import groupby, pairwise
from typing import Final, cast

import deal
import polars as pl

from intervals.config import (
    COASTING_POWER_W,
    OTSU_BINS,
    SMOOTHING_WINDOW_S,
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
        or _.result["smoothed_power"]
        .drop_nulls()
        .is_between(_.series["power"].min(), _.series["power"].max())
        .all()
    )
)
def smooth_power(series: pl.DataFrame) -> pl.DataFrame:
    """Damp the second-to-second chatter out of a ride's power signal.

    Raw 1 Hz power is far too noisy to threshold directly: it swings by a
    median of ~12 W per second even in the middle of a steady effort, so
    any fixed threshold on the raw signal is crossed back and forth
    constantly and shatters one real effort into dozens of fragments.
    Averaging over ``SMOOTHING_WINDOW_S`` removes that chatter while
    keeping a block's start and end within a few seconds of where they
    really are.

    Args:
        series: A 1 Hz-gridded time series with a ``power`` column, as
            returned by :func:`resample_to_1hz`; must not be empty.

    Returns:
        ``series`` with an added ``smoothed_power`` column: the centred
        rolling mean of ``power``, in watts. Null power readings (a gap,
        or no power meter at all) are skipped rather than treated as zero;
        a second with no non-null power within its window is null. The
        window shrinks at both ends of the ride rather than padding with
        invented values.

    Raises:
        deal.PreContractError: If ``series`` is empty or not spaced exactly
            one second apart.

    >>> from datetime import UTC, datetime
    >>> records = [
    ...     RecordPoint(
    ...         timestamp=datetime(2026, 7, 16, 14, 0, i, tzinfo=UTC), power=200
    ...     )
    ...     for i in range(5)
    ... ]
    >>> smooth_power(resample_to_1hz(records))["smoothed_power"].to_list()
    [200.0, 200.0, 200.0, 200.0, 200.0]
    """
    return series.with_columns(
        pl.col("power")
        .cast(pl.Float64)
        .rolling_mean(SMOOTHING_WINDOW_S, center=True, min_samples=1)
        .alias("smoothed_power")
    )


def _power_histogram(values: list[float], lowest: float, width: float) -> list[int]:
    """Count how many values fall into each of ``OTSU_BINS`` equal bins.

    >>> _power_histogram([100.0, 100.0, 300.0], 100.0, 100.0)[:3]
    [2, 0, 1]
    """
    counts = [0] * OTSU_BINS
    for value in values:
        index = min(int((value - lowest) / width), OTSU_BINS - 1)
        counts[index] += 1
    return counts


@deal.pre(lambda series: len(series) > 0)
@deal.pre(lambda series: "smoothed_power" in series.columns)
@deal.ensure(lambda _: _.result is None or _.result > COASTING_POWER_W)
def effort_threshold(series: pl.DataFrame) -> float | None:
    """Find the power that best separates a ride's easy seconds from its hard ones.

    Interval detection needs a reference to call a stretch "hard", and that
    reference has to come from the ride itself — one athlete's easy pace is
    another's threshold. Rather than fixing a level and a factor, this splits
    the ride's own power readings into two classes and returns the boundary
    that separates them best, in the sense of Otsu's method: the cut that
    maximises the variance *between* the two classes.

    Two earlier references were tried and discarded (see
    ``docs/entscheidungen.md``). A local rolling quantile rises along with
    the very effort it is supposed to measure against and ends a long block
    from within. A ride-global median fails whenever the intervals make up
    more than half the ride — a 5x4min session sits above its own median,
    so nothing clears the threshold at all. A two-class split has neither
    problem, because it is driven by the gap between the classes rather
    than by how much time is spent in either.

    Coasting is excluded first: a long descent says nothing about how hard
    the ride was, and leaving it in creates a spurious third class.

    Args:
        series: A 1 Hz-gridded time series with a ``smoothed_power``
            column, as returned by :func:`smooth_power`; must not be
            empty.

    Returns:
        The separating power in watts, strictly above
        ``COASTING_POWER_W``, or None if the ride has no pedalling second
        at all (no power meter, or spent entirely coasting) or holds its
        power perfectly constant, leaving nothing to separate.

    Raises:
        deal.PreContractError: If ``series`` is empty or has no
            ``smoothed_power`` column.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start + timedelta(seconds=i), power=p)
    ...     for i, p in enumerate([100] * 120 + [300] * 120)
    ... ]
    >>> threshold = effort_threshold(smooth_power(resample_to_1hz(records)))
    >>> 100 < threshold < 300
    True
    """
    smoothed = series["smoothed_power"].drop_nulls()
    pedalling = smoothed.filter(smoothed > COASTING_POWER_W)
    if pedalling.len() == 0:
        return None
    lowest = cast(float, pedalling.min())
    highest = cast(float, pedalling.max())
    if highest <= lowest:
        return None

    width = (highest - lowest) / OTSU_BINS
    counts = _power_histogram(pedalling.to_list(), lowest, width)
    centre = [lowest + (index + 0.5) * width for index in range(OTSU_BINS)]
    total_count = pedalling.len()
    total_weighted = sum(count * mid for count, mid in zip(counts, centre, strict=True))

    best_boundary, best_variance = 1, -1.0
    below_count, below_weighted = 0, 0.0
    for boundary in range(1, OTSU_BINS):
        below_count += counts[boundary - 1]
        below_weighted += counts[boundary - 1] * centre[boundary - 1]
        above_count = total_count - below_count
        if below_count == 0 or above_count == 0:
            continue
        below_mean = below_weighted / below_count
        above_mean = (total_weighted - below_weighted) / above_count
        # Between-class variance, without the constant 1/total_count**2 that
        # would scale every candidate equally and change no comparison.
        variance = below_count * above_count * (below_mean - above_mean) ** 2
        if variance > best_variance:
            best_boundary, best_variance = boundary, variance
    return lowest + best_boundary * width


def has_strictly_increasing_timestamps(records: list[RecordPoint]) -> bool:
    """Whether ``records`` satisfies :func:`resample_to_1hz`'s timing invariant.

    That function requires strictly increasing timestamps as a contract
    precondition — a legitimate invariant for internal callers, but records
    coming from a validated, real-world FIT file only guarantee
    non-decreasing order. Two samples sharing a timestamp is thus a
    possible real state, not a bug, and must not reach that contract as a
    crash. Callers check this first and skip the ride instead.

    Args:
        records: The workout's record points.

    Returns:
        True if every timestamp is strictly later than the one before it.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> clean = [RecordPoint(timestamp=start + timedelta(seconds=i)) for i in range(3)]
    >>> has_strictly_increasing_timestamps(clean)
    True
    >>> has_strictly_increasing_timestamps([clean[0], clean[0]])
    False
    """
    return all(
        earlier.timestamp < later.timestamp for earlier, later in pairwise(records)
    )
