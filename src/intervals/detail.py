"""The close-up on one detected interval: its own rows and its own numbers."""

import deal
import polars as pl
from pydantic import BaseModel, NonNegativeFloat

from analysis import average
from intervals.blocks import IntervalBlock


# One combined condition rather than two stacked @deal.pre decorators:
# their evaluation order is not the source order, so a separate emptiness
# check would not reliably run before the indexing below it.
@deal.pre(
    lambda series, block: (
        len(series) > 0
        and series["timestamp"][0] <= block.start <= series["timestamp"][-1]
    )
)
@deal.ensure(lambda _: len(_.result) > 0)
def slice_block(series: pl.DataFrame, block: IntervalBlock) -> pl.DataFrame:
    """Cut the rows belonging to one block out of the workout's time series.

    ``block.end`` is the second *after* the block's last recorded one (see
    :func:`~intervals.blocks.build_interval_block`), so the upper bound is
    exclusive and two adjacent blocks never share a row.

    Args:
        series: The 1 Hz-gridded series the block was detected on; must not
            be empty and must contain the block's start.
        block: The block to cut out.

    Returns:
        The block's rows, in chronological order. Never empty: the
        preconditions place the block's start inside a gapless 1 Hz grid.

    Raises:
        deal.PreContractError: If ``series`` is empty or the block starts
            outside it — both mean the block came from a different workout
            than the series it is being cut from.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> series = pl.DataFrame(
    ...     {
    ...         "timestamp": [start + timedelta(seconds=i) for i in range(5)],
    ...         "power": [100, 200, 210, 220, 100],
    ...     }
    ... )
    >>> block = IntervalBlock(
    ...     start=start + timedelta(seconds=1),
    ...     end=start + timedelta(seconds=4),
    ...     duration=timedelta(seconds=3),
    ...     avg_power_w=210.0,
    ...     avg_power_relative_to_ftp=None,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=1.0,
    ... )
    >>> slice_block(series, block)["power"].to_list()
    [200, 210, 220]
    """
    return series.filter(
        pl.col("timestamp").is_between(block.start, block.end, closed="left")
    )


class BlockDetail(BaseModel):
    """The per-interval numbers that the block report itself does not carry.

    :class:`~intervals.blocks.IntervalBlock` reports what a block looks
    like next to its siblings — averages, drift, evenness. These are the
    figures that only make sense once a single block is looked at on its
    own.

    Attributes:
        max_power_w: Highest single-second power reading in the block. Read
            against the block's average, it says how much of the effort was
            spikes rather than steady work.
        avg_cadence: Mean pedalling cadence in rpm, or None if no cadence
            was recorded.
        heart_rate_start: First recorded heart rate in the block, or None if
            none was recorded. Together with ``heart_rate_end`` this is the
            literal ramp the athlete rode, where
            :attr:`IntervalBlock.heart_rate_drift_bpm` compares the block's
            two halves — steadier, but it hides the endpoints.
        heart_rate_end: Last recorded heart rate in the block, or None if
            none was recorded.
    """

    max_power_w: NonNegativeFloat
    avg_cadence: NonNegativeFloat | None
    heart_rate_start: NonNegativeFloat | None
    heart_rate_end: NonNegativeFloat | None


@deal.pre(lambda block_series: block_series["power"].drop_nulls().len() > 0)
def block_detail(block_series: pl.DataFrame) -> BlockDetail:
    """Compute the close-up figures for a single block's rows.

    Nulls are skipped rather than counted as zero, matching how
    :func:`~intervals.blocks.build_interval_block` treats a recording gap
    inside a block.

    Args:
        block_series: One block's rows as returned by :func:`slice_block`,
            with ``power``, ``cadence`` and ``heart_rate`` columns; must
            hold at least one power reading.

    Returns:
        The block's close-up figures.

    Raises:
        deal.PreContractError: If the rows hold no power reading at all — a
            detected block always spans more than the smoothing window and
            so always contains one.

    >>> block_series = pl.DataFrame(
    ...     {
    ...         "power": [200, None, 260],
    ...         "cadence": [90, 92, 94],
    ...         "heart_rate": [140, 150, 160],
    ...     }
    ... )
    >>> detail = block_detail(block_series)
    >>> detail.max_power_w, detail.avg_cadence
    (260.0, 92.0)
    >>> detail.heart_rate_start, detail.heart_rate_end
    (140.0, 160.0)
    """
    powers = [power for power in block_series["power"].to_list() if power is not None]
    cadences = [
        cadence for cadence in block_series["cadence"].to_list() if cadence is not None
    ]
    heart_rates = [
        rate for rate in block_series["heart_rate"].to_list() if rate is not None
    ]

    return BlockDetail(
        max_power_w=max(powers),
        avg_cadence=average(cadences) if cadences else None,
        heart_rate_start=heart_rates[0] if heart_rates else None,
        heart_rate_end=heart_rates[-1] if heart_rates else None,
    )
