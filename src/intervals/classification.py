"""Naming a detected interval block by the kind of training it represents."""

from collections import Counter
from enum import StrEnum
from typing import Final

import deal

from intervals.blocks import IntervalBlock


class IntervalType(StrEnum):
    """The kind of training a detected interval block represents.

    Named by training intent rather than by power zone. The bands overlap
    the zone table in :mod:`analysis.power_zones` on purpose: a zone chart
    answers how a ride's seconds were distributed, while this answers what
    kind of session was ridden, and cyclists name those sessions after the
    effort they intended. A block at 93 % of FTP is therefore "Sweet Spot"
    here while its seconds sit in the zone chart's threshold zone.

    Attributes:
        TEMPO: Up to 84 % of FTP — sustained work below the sweet spot.
        SWEET_SPOT: 84–97 % of FTP.
        SCHWELLE: 97–105 % of FTP, work at the threshold itself.
        VO2MAX: 105–120 % of FTP.
        ANAEROB: Above 120 % of FTP. Reachable in principle but rare in
            practice, since blocks shorter than
            :data:`~intervals.config.MIN_BLOCK_DURATION_S` are never
            detected and efforts this hard are seldom longer.
        GEMISCHT: A session whose blocks tie between two types. Produced
            only by :func:`classify_session`, never for a single block.
    """

    TEMPO = "tempo"
    SWEET_SPOT = "sweet_spot"
    SCHWELLE = "schwelle"
    VO2MAX = "vo2max"
    ANAEROB = "anaerob"
    GEMISCHT = "gemischt"


_TYPE_BANDS: Final[tuple[tuple[IntervalType, float | None], ...]] = (
    (IntervalType.TEMPO, 0.84),
    (IntervalType.SWEET_SPOT, 0.97),
    (IntervalType.SCHWELLE, 1.05),
    (IntervalType.VO2MAX, 1.20),
    (IntervalType.ANAEROB, None),
)
"""Each type with the upper bound of its band as a fraction of FTP, in
ascending order; the bound is inclusive and the top band is open-ended
(``None``), following the same shape as
``analysis.power_zones._ZONE_FRACTIONS``. Only the average power decides the
type — duration does not, because twenty minutes at threshold and three
minutes at threshold are the same kind of work in different portions."""


@deal.pre(lambda relative_power: relative_power >= 0)
@deal.ensure(lambda _: _.result is not IntervalType.GEMISCHT)
def classify_relative_power(relative_power: float) -> IntervalType:
    """Name the training type for a power given as a fraction of FTP.

    Args:
        relative_power: Power divided by FTP, e.g. 0.95 for 95 % of FTP;
            must not be negative.

    Returns:
        The type whose band the power falls into. Never
        :attr:`IntervalType.GEMISCHT`, which describes a whole session
        rather than one power.

    Raises:
        deal.PreContractError: If ``relative_power`` is negative.

    >>> classify_relative_power(0.70)
    <IntervalType.TEMPO: 'tempo'>
    >>> classify_relative_power(0.92)
    <IntervalType.SWEET_SPOT: 'sweet_spot'>
    >>> classify_relative_power(1.00)
    <IntervalType.SCHWELLE: 'schwelle'>
    >>> classify_relative_power(1.60)
    <IntervalType.ANAEROB: 'anaerob'>

    The upper bound belongs to its own band:

    >>> classify_relative_power(0.84)
    <IntervalType.TEMPO: 'tempo'>
    """
    for interval_type, upper_bound in _TYPE_BANDS:
        if upper_bound is None or relative_power <= upper_bound:
            return interval_type
    # Unreachable: the last band is open-ended, so the loop always returns.
    raise AssertionError("no band matched")


def classify_block(block: IntervalBlock) -> IntervalType | None:
    """Name the training type of a single detected block.

    Args:
        block: The detected block.

    Returns:
        The block's type, or None if the athlete's FTP is unknown — the
        bands are defined relative to it, so without it there is nothing
        to compare the power against.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> block = IntervalBlock(
    ...     start=start,
    ...     end=start + timedelta(minutes=8),
    ...     duration=timedelta(minutes=8),
    ...     avg_power_w=220.0,
    ...     avg_power_relative_to_ftp=0.88,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=0.95,
    ... )
    >>> classify_block(block)
    <IntervalType.SWEET_SPOT: 'sweet_spot'>
    >>> classify_block(block.model_copy(update={"avg_power_relative_to_ftp": None}))
    """
    if block.avg_power_relative_to_ftp is None:
        return None
    return classify_relative_power(block.avg_power_relative_to_ftp)


@deal.pre(lambda blocks: len(blocks) > 0)
def classify_session(blocks: list[IntervalBlock]) -> IntervalType | None:
    """Name the training type of a whole session from its blocks.

    The type most of the blocks share wins, rather than requiring them all
    to agree: repetitions ridden close to a band edge scatter across two
    bands, and calling such a session mixed would hide what it plainly
    was. Only a genuine tie — two types reaching the same count, as with
    two blocks of different type — yields :attr:`IntervalType.GEMISCHT`.

    Args:
        blocks: The session's detected blocks; must not be empty.

    Returns:
        The session's type, or None if none of the blocks could be typed
        because the athlete's FTP is unknown.

    Raises:
        deal.PreContractError: If ``blocks`` is empty.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> block = IntervalBlock(
    ...     start=start,
    ...     end=start + timedelta(minutes=8),
    ...     duration=timedelta(minutes=8),
    ...     avg_power_w=220.0,
    ...     avg_power_relative_to_ftp=1.00,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=0.95,
    ... )
    >>> sweet_spot = block.model_copy(update={"avg_power_relative_to_ftp": 0.90})
    >>> classify_session([block, block, sweet_spot])
    <IntervalType.SCHWELLE: 'schwelle'>
    >>> classify_session([block, sweet_spot])
    <IntervalType.GEMISCHT: 'gemischt'>
    """
    types = [
        block_type
        for block in blocks
        if (block_type := classify_block(block)) is not None
    ]
    if not types:
        return None

    counts = Counter(types)
    highest = max(counts.values())
    leaders = [block_type for block_type, count in counts.items() if count == highest]
    return leaders[0] if len(leaders) == 1 else IntervalType.GEMISCHT


@deal.pre(lambda interval_type: interval_type is not IntervalType.GEMISCHT)
@deal.ensure(lambda _: _.result[1] is None or _.result[0] < _.result[1])
def relative_power_band(interval_type: IntervalType) -> tuple[float, float | None]:
    """The band of relative power a type covers, as ``(lower, upper)``.

    The inverse of :func:`classify_relative_power`, for callers that start
    from a type and need a power rather than the other way round — a
    training recommendation naming a target wattage, for instance.

    Args:
        interval_type: The type to look up; not
            :attr:`IntervalType.GEMISCHT`, which describes a session
            rather than a power and so has no band.

    Returns:
        The band's lower bound (exclusive, 0.0 for the lowest type) and
        its upper bound (inclusive), which is None for the open-ended top
        band.

    Raises:
        deal.PreContractError: If asked for
            :attr:`IntervalType.GEMISCHT`.

    >>> relative_power_band(IntervalType.SWEET_SPOT)
    (0.84, 0.97)
    >>> relative_power_band(IntervalType.TEMPO)
    (0.0, 0.84)
    >>> relative_power_band(IntervalType.ANAEROB)
    (1.2, None)
    """
    lower = 0.0
    for candidate, upper in _TYPE_BANDS:
        if candidate is interval_type:
            return lower, upper
        if upper is not None:
            lower = upper
    # Unreachable: every type except GEMISCHT appears in the band table,
    # and the precondition rules that one out.
    raise AssertionError("no band for this type")
