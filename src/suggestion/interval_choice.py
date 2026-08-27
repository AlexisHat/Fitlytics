"""Picking which kind of intervals to ride, from what was ridden lately."""

from collections import Counter
from datetime import date
from random import Random
from typing import Final

import deal

from intervals import IntervalType
from suggestion.history import SessionSummary

SUGGESTABLE_TYPES: Final[tuple[IntervalType, ...]] = (
    IntervalType.SWEET_SPOT,
    IntervalType.SCHWELLE,
    IntervalType.VO2MAX,
)
"""The types a recommendation may name, from easiest to hardest.

The other three are deliberately absent. GEMISCHT is an analysis result
rather than a session anyone sets out to ride. ANAEROB lives in efforts
shorter than :data:`~intervals.config.MIN_BLOCK_DURATION_S`, so this app
could never confirm afterwards that it was ridden. TEMPO sits below the
sweet spot and is base training by another name, which the coarse decision
already covers."""


@deal.ensure(lambda _: _.result in SUGGESTABLE_TYPES)
def choose_interval_type(sessions: list[SessionSummary], today: date) -> IntervalType:
    """Pick the type that has come up least often in the recent sessions.

    Rotating towards what is missing keeps a training block from drifting
    into whichever session the athlete happens to enjoy most. A type absent
    from the window counts as zero, so an untouched type always wins over
    one already ridden.

    Ties are broken with a generator seeded from the date. True randomness
    would reshuffle the suggestion on every Streamlit rerun — that is, on
    every click — so the athlete would watch it flicker. Seeding from the
    day gives an unpredictable-looking choice that nevertheless holds still
    for the whole day, and one that tests can reproduce.

    Args:
        sessions: The recent sessions, as returned by
            :func:`~suggestion.history.recent_sessions`. May be empty.
        today: The day being planned, used to seed the tie-break.

    Returns:
        One of :data:`SUGGESTABLE_TYPES`.

    >>> from datetime import date
    >>> def ridden(interval_type: IntervalType) -> SessionSummary:
    ...     return SessionSummary(
    ...         date=date(2026, 7, 1), category=None, interval_type=interval_type
    ...     )
    >>> sessions = [ridden(IntervalType.SWEET_SPOT), ridden(IntervalType.SCHWELLE)]
    >>> choose_interval_type(sessions, date(2026, 7, 20))
    <IntervalType.VO2MAX: 'vo2max'>

    A tie between two untouched types settles the same way all day:

    >>> one_ridden = [ridden(IntervalType.VO2MAX)]
    >>> first = choose_interval_type(one_ridden, date(2026, 7, 20))
    >>> first is choose_interval_type(one_ridden, date(2026, 7, 20))
    True
    >>> first in SUGGESTABLE_TYPES
    True
    """
    counts = Counter(
        session.interval_type
        for session in sessions
        if session.interval_type in SUGGESTABLE_TYPES
    )
    fewest = min(counts[interval_type] for interval_type in SUGGESTABLE_TYPES)
    candidates = [
        interval_type
        for interval_type in SUGGESTABLE_TYPES
        if counts[interval_type] == fewest
    ]
    if len(candidates) == 1:
        return candidates[0]
    return Random(today.toordinal()).choice(candidates)
