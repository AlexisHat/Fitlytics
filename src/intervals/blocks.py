"""Turning a detected candidate window into the interval block report.

Everything upstream (:mod:`intervals.candidates`, :mod:`intervals.merging`,
:mod:`intervals.filtering`) works on plain ``(start_index, end_index)``
row-index pairs. This module is where those become the actual reported
numbers: duration, average power and heart rate, heart rate drift and
evenness — the "Erkennung, Ø-Watt, Ø-Puls, Pulsentwicklung,
Gleichmäßigkeit" the project sketch asks for.
"""

from datetime import datetime, timedelta
from typing import cast

import deal
import polars as pl
from pydantic import BaseModel, NonNegativeFloat

from analysis import average


class IntervalBlock(BaseModel):
    """One detected interval block within a workout.

    Attributes:
        start: Start of the block.
        end: End of the block.
        duration: ``end - start``.
        avg_power_w: Mean power within the block, in watts.
        avg_power_relative_to_ftp: ``avg_power_w / ftp_watts``, or None if
            the athlete's FTP is unknown.
        avg_heart_rate: Mean heart rate within the block, in bpm, or None
            if no heart rate was recorded.
        heart_rate_drift_bpm: Mean heart rate of the block's second half
            minus its first half — positive means heart rate rose over the
            block (cardiac drift). None if fewer than two heart rate
            samples were recorded.
        evenness: How steady the block's power was: 1 minus the
            coefficient of variation (std / mean) of power within the
            block. 1.0 is perfectly steady; lower means more variable.
    """

    start: datetime
    end: datetime
    duration: timedelta
    avg_power_w: NonNegativeFloat
    avg_power_relative_to_ftp: NonNegativeFloat | None
    avg_heart_rate: NonNegativeFloat | None
    heart_rate_drift_bpm: float | None
    evenness: float


@deal.pre(lambda series, candidate, ftp_watts=None: candidate[0] < candidate[1])
@deal.post(lambda result: result.start < result.end)
def build_interval_block(
    series: pl.DataFrame, candidate: tuple[int, int], ftp_watts: int | None = None
) -> IntervalBlock:
    """Build the report for one detected candidate window.

    Args:
        series: The time series the candidate was found on, with
            ``timestamp``, ``power`` and ``heart_rate`` columns.
        candidate: The block's ``(start_index, end_index)``; ``start_index``
            must be before ``end_index``.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown.

    Returns:
        The block's report.

    Raises:
        deal.PreContractError: If ``candidate`` is not a valid, ordered
            index pair.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(4)],
    ...         "power": [200, 220, 240, 260],
    ...         "heart_rate": [140, 145, 150, 155],
    ...     }
    ... )
    >>> block = build_interval_block(series, (0, 4), ftp_watts=250)
    >>> block.avg_power_w, block.avg_power_relative_to_ftp
    (230.0, 0.92)
    >>> block.heart_rate_drift_bpm
    10.0
    """
    start_index, end_index = candidate
    block = series[start_index:end_index]
    # series may not have a row *at* end_index (a block running to the very
    # last recorded second, with no further data) — derive the end instead
    # of indexing series["timestamp"][end_index], which would be out of
    # bounds in exactly that case.
    start = block["timestamp"][0]
    end = block["timestamp"][-1] + timedelta(seconds=1)

    avg_power = average(block["power"].to_list())
    mean_power = cast(float, block["power"].mean())
    std_power = block["power"].std()
    evenness = 1 - cast(float, std_power) / mean_power if mean_power else 1.0

    heart_rates = [hr for hr in block["heart_rate"].to_list() if hr is not None]
    midpoint = len(heart_rates) // 2
    heart_rate_drift = (
        average(heart_rates[midpoint:]) - average(heart_rates[:midpoint])
        if len(heart_rates) >= 2
        else None
    )

    return IntervalBlock(
        start=start,
        end=end,
        duration=end - start,
        avg_power_w=avg_power,
        avg_power_relative_to_ftp=avg_power / ftp_watts if ftp_watts else None,
        avg_heart_rate=average(heart_rates) if heart_rates else None,
        heart_rate_drift_bpm=heart_rate_drift,
        evenness=evenness,
    )


def build_interval_blocks(
    series: pl.DataFrame,
    candidates: list[tuple[int, int]],
    ftp_watts: int | None = None,
) -> list[IntervalBlock]:
    """Build the report for every detected candidate window.

    Args:
        series: The time series the candidates were found on, with
            ``timestamp``, ``power`` and ``heart_rate`` columns.
        candidates: The detected blocks' ``(start_index, end_index)``
            pairs, as returned by
            :func:`~intervals.filtering.find_candidates`.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown.

    Returns:
        One report per candidate, in the same order.
    """
    return [
        build_interval_block(series, candidate, ftp_watts) for candidate in candidates
    ]
