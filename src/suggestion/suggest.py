"""The finished recommendation: what to ride today, and at what power."""

from datetime import date
from typing import Final

import deal
from pydantic import BaseModel, PositiveInt

from intervals import IntervalType, relative_power_band
from models import WorkoutCategory
from suggestion.history import SessionSummary
from suggestion.interval_choice import choose_interval_type
from suggestion.rules import RECOVERY_YELLOW_MAX, CategoryDecision, decide_category

GRUNDLAGE_BAND: Final[tuple[float, float]] = (0.55, 0.75)
"""Relative-power band for a base ride: the endurance zone of the Coggan
model already used for the zone charts (``analysis.power_zones``), so the
suggested wattage lands in the same zone the chart will later show it in."""

RECOVERY_BAND: Final[tuple[float, float]] = (0.45, 0.55)
"""Relative-power band for a recovery ride, topping out at the same 55 % of
FTP where the Coggan model ends its active-recovery zone."""


class TrainingSuggestion(BaseModel):
    """What the athlete should ride today.

    Attributes:
        decision: The coarse decision and the rule behind it.
        interval_type: Which kind of intervals, set only when
            :attr:`CategoryDecision.category` is
            :attr:`~models.WorkoutCategory.INTERVALLE`.
        target_power_w: The wattage to aim for, or None if no FTP is known
            to scale the band to.
    """

    decision: CategoryDecision
    interval_type: IntervalType | None
    target_power_w: PositiveInt | None


def _band_for(
    category: WorkoutCategory, interval_type: IntervalType | None
) -> tuple[float, float]:
    """The relative-power band the target wattage is taken from."""
    if category is WorkoutCategory.RECOVERY:
        return RECOVERY_BAND
    if category is not WorkoutCategory.INTERVALLE or interval_type is None:
        return GRUNDLAGE_BAND

    lower, upper = relative_power_band(interval_type)
    # Only ANAEROB is open-ended, and it is never suggested — see
    # SUGGESTABLE_TYPES. Collapsing the band keeps the types honest here
    # rather than inventing a ceiling for a case that cannot arise.
    return (lower, upper) if upper is not None else (lower, lower)


def _target_fraction(band: tuple[float, float], recovery_score: int | None) -> float:
    """Where within the band to aim, given how recovered the athlete is.

    A yellow recovery day drops the target to the band's lower edge rather
    than subtracting an invented percentage. The session then still is what
    it was prescribed as — a sweet-spot ride stays a sweet-spot ride — just
    at its gentlest end, and the reduction is derived from the same band
    table the type itself comes from.
    """
    lower, upper = band
    if recovery_score is not None and recovery_score <= RECOVERY_YELLOW_MAX:
        return lower
    return (lower + upper) / 2


@deal.pre(
    lambda sessions, today, ftp_watts=None, recovery_score=None: (
        recovery_score is None or 0 <= recovery_score <= 100
    )
)
@deal.pre(
    lambda sessions, today, ftp_watts=None, recovery_score=None: (
        ftp_watts is None or ftp_watts > 0
    )
)
@deal.ensure(
    lambda _: (
        (_.result.interval_type is not None)
        == (_.result.decision.category is WorkoutCategory.INTERVALLE)
    )
)
def suggest_training(
    sessions: list[SessionSummary],
    today: date,
    ftp_watts: int | None = None,
    recovery_score: int | None = None,
) -> TrainingSuggestion:
    """Recommend today's session from the recent ones and today's recovery.

    Two stages: :func:`~suggestion.rules.decide_category` settles whether
    today is a hard day at all, and only then does
    :func:`~suggestion.interval_choice.choose_interval_type` pick which
    kind. Keeping them apart means the rest rules never have to reason
    about interval types, and the type rotation never has to reason about
    fatigue.

    Args:
        sessions: The recent sessions, oldest first.
        today: The day being planned.
        ftp_watts: The athlete's current FTP, or None if unknown; must be
            positive if given.
        recovery_score: Today's Whoop recovery score in percent, or None
            if no recovery data covers today.

    Returns:
        The category, the interval type where one applies, and the target
        wattage where an FTP is known.

    Raises:
        deal.PreContractError: If ``recovery_score`` is outside 0–100 or
            ``ftp_watts`` is not positive.

    >>> from datetime import date
    >>> from models import WorkoutCategory
    >>> from suggestion.interval_choice import SUGGESTABLE_TYPES
    >>> easy = [
    ...     SessionSummary(
    ...         date=date(2026, 7, day),
    ...         category=WorkoutCategory.GRUNDLAGE,
    ...         interval_type=None,
    ...     )
    ...     for day in (10, 12, 14)
    ... ]
    >>> suggestion = suggest_training(easy, date(2026, 7, 20), ftp_watts=223)
    >>> suggestion.decision.category
    <WorkoutCategory.INTERVALLE: 'intervalle'>
    >>> suggestion.interval_type in SUGGESTABLE_TYPES
    True

    Without an FTP there is a session to ride but no wattage to name:

    >>> suggest_training(easy, date(2026, 7, 20)).target_power_w is None
    True
    """
    decision = decide_category(sessions, today, recovery_score)
    interval_type = (
        choose_interval_type(sessions, today)
        if decision.category is WorkoutCategory.INTERVALLE
        else None
    )

    band = _band_for(decision.category, interval_type)
    target_power_w = (
        round(_target_fraction(band, recovery_score) * ftp_watts)
        if ftp_watts is not None
        else None
    )
    return TrainingSuggestion(
        decision=decision,
        interval_type=interval_type,
        target_power_w=target_power_w,
    )
