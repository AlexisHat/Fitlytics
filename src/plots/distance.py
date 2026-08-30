"""Turning a workout's raw distance signal into a chartable x-axis.

Two problems keep a workout's own distance from being usable as an x-axis
directly. Some devices never record cumulative distance at all — only
speed — so a value has to be derived. And even where distance is recorded,
a standstill (red light, gate) or a GPS glitch can produce several samples
at the same or a lower distance than the one before, which plots as a
vertical jump or a fold-back rather than a smooth line. Both are resolved
here, once, before any panel is built from the result.
"""

from itertools import pairwise
from typing import Final

import deal
import polars as pl

from errors import AnalysisError
from plots.series import trim_to_first_fully_measured_row

_KMH_TO_KM_PER_SECOND: Final = 1 / 3600
"""Converts a speed in km/h and a duration in seconds directly to
kilometres travelled, without a detour through metres or m/s."""


def _integrate_distance_km(series: pl.DataFrame) -> pl.Series:
    """Integrate cumulative distance from speed and elapsed time.

    Used only when the workout has no distance field of its own — some
    head units record speed without ever accumulating a running total.
    Each second's distance is that second's speed held constant since the
    previous sample (the same sample-and-hold convention used elsewhere in
    the project, e.g. for heart-rate zone time). A gap with no speed
    reading contributes no distance rather than inventing one.

    Args:
        series: A time series built by
            :func:`~plots.series.build_time_series`, with ``elapsed_s`` and
            ``speed_kmh`` columns.

    Returns:
        Cumulative distance in kilometres, one value per row, starting at
        0.0 and only ever increasing or holding steady.

    >>> series = pl.DataFrame(
    ...     {"elapsed_s": [0.0, 1.0, 2.0], "speed_kmh": [0.0, 36.0, 36.0]}
    ... )
    >>> _integrate_distance_km(series).to_list()
    [0.0, 0.01, 0.02]
    """
    dt = pl.col("elapsed_s").diff().fill_null(0.0)
    increment_km = pl.col("speed_kmh").fill_null(0.0) * dt * _KMH_TO_KM_PER_SECOND
    return series.select(increment_km.cum_sum().alias("distance_km"))["distance_km"]


@deal.pre(lambda series: len(series) > 0)
def _strictly_increasing_by_distance(series: pl.DataFrame) -> pl.DataFrame:
    """Collapse a standstill or GPS glitch into a single, later point.

    First clamps any regression (a GPS position jumping backward, a
    distance counter that briefly resets) to the highest distance seen so
    far, using a running maximum. That alone still leaves runs of *equal*
    distance — every second of a red-light stop reports the same total —
    which plot as several points stacked on one x position, a vertical
    artefact rather than a real shape. Collapsing each such run to its
    last row removes those ties, leaving every remaining row's distance
    strictly greater than the one before, while still keeping one
    representative (the freshest) reading from the stop.

    Args:
        series: A time series with a ``distance_km`` column that has no
            leading nulls; must not be empty.

    Returns:
        The subset of ``series``, in order, whose ``distance_km`` values
        are strictly increasing.

    Raises:
        deal.PreContractError: If ``series`` is empty.

    >>> series = pl.DataFrame({"distance_km": [0.0, 1.0, 1.0, 1.0, 0.9, 2.0]})
    >>> _strictly_increasing_by_distance(series)["distance_km"].to_list()
    [0.0, 1.0, 2.0]
    """
    bounded = series.with_columns(pl.col("distance_km").cum_max())
    keep_last_of_run = (
        pl.col("distance_km") != pl.col("distance_km").shift(-1)
    ).fill_null(True)
    return bounded.filter(keep_last_of_run)


@deal.pre(lambda series: len(series) > 0)
@deal.ensure(
    lambda _: all(a < b for a, b in pairwise(_.result["distance_km"].to_list()))
)
def prepare_distance_axis(series: pl.DataFrame) -> pl.DataFrame:
    """Resolve and clean a workout's distance so it can drive an x-axis.

    Args:
        series: A time series built by
            :func:`~plots.series.build_time_series`; must not be empty.

    Returns:
        ``series``, restricted to rows with a strictly increasing
        ``distance_km``: sourced from the workout's own recorded distance
        where available (falling back to speed integration, see
        :func:`_integrate_distance_km`), with any leading rows before
        distance is known dropped, and standstills or GPS noise collapsed
        (see :func:`_strictly_increasing_by_distance`).

    Raises:
        deal.PreContractError: If ``series`` is empty.
        AnalysisError: If the workout never progresses far enough for two
            distinct distance readings to remain — no distance and no
            speed at all, or one that never leaves a single spot.

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=i), distance_m=float(i * 5)
    ...     )
    ...     for i in range(3)
    ... ]
    >>> prepare_distance_axis(build_time_series(records))["distance_km"].to_list()
    [0.0, 0.005, 0.01]
    """
    has_distance = series["distance_km"].drop_nulls().len() > 0
    distance_km = (
        series["distance_km"] if has_distance else _integrate_distance_km(series)
    )
    with_distance = series.with_columns(distance_km.alias("distance_km"))

    trimmed = trim_to_first_fully_measured_row(with_distance, ["distance_km"])
    filled = trimmed.with_columns(pl.col("distance_km").fill_null(strategy="forward"))
    cleaned = _strictly_increasing_by_distance(filled)

    if len(cleaned) < 2:
        raise AnalysisError(
            "not enough distance progression to build a distance-based timeline"
        )
    return cleaned
