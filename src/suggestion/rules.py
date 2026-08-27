"""Deciding whether today should be intervals, base training, or recovery."""

from datetime import date, timedelta
from enum import StrEnum
from typing import Final

import deal
from pydantic import BaseModel, NonNegativeInt

from models import WorkoutCategory
from suggestion.history import SessionSummary

SUGGESTABLE_CATEGORIES: Final = frozenset(
    {
        WorkoutCategory.GRUNDLAGE,
        WorkoutCategory.INTERVALLE,
        WorkoutCategory.RECOVERY,
    }
)
"""The categories a recommendation may name. The remaining two exist for
tagging what was ridden, not for planning it: a group ride is arranged with
other people rather than prescribed, and "Sonstige" is a catch-all."""

MAX_HARD_SESSIONS: Final = 2
"""How many of the last :data:`~suggestion.history.WINDOW_SIZE` sessions may
be interval sessions before base training is due instead.

The polarized-training literature's 80/20 split is measured in training
*time*, while this window counts *sessions*. Two hard sessions a week out of
four to six rides is the common prescription for trained amateurs, and since
interval sessions are the shorter ones, two out of five sessions lands at
roughly a fifth to a quarter of training time at high intensity — the same
place the literature points to, expressed in what this app can actually
count."""

RECOVERY_RED_MAX: Final = 33
"""Whoop's own upper bound for the red recovery band. Adopted rather than
derived: the scores come from Whoop, and the athlete reads the same three
bands in Whoop's own app, so a second set of boundaries here would only
disagree with what they already see."""

RECOVERY_YELLOW_MAX: Final = 66
"""Upper bound of Whoop's yellow band; above it the day counts as green."""

_HARD_SESSION_REST_DAYS: Final = 1
"""How many days must pass after an interval session before another is
suggested. One day, not two: at two, an athlete riding three times a week
would practically never see an interval session suggested again."""


class SuggestionReason(StrEnum):
    """Why a recommendation came out the way it did.

    Kept as an enum rather than a sentence so the wording stays in the
    view layer, like :class:`~intervals.classification.IntervalType`.

    Attributes:
        NO_HISTORY: Nothing has been ridden yet to reason from.
        LOW_RECOVERY: Today's recovery score is in the red band.
        HARD_SESSION_RECENTLY: An interval session falls within the last
            :data:`_HARD_SESSION_REST_DAYS` days.
        ENOUGH_HARD_SESSIONS: The window already holds
            :data:`MAX_HARD_SESSIONS` interval sessions.
        HARD_SESSION_DUE: Nothing stands in the way of intervals today.
    """

    NO_HISTORY = "no_history"
    LOW_RECOVERY = "low_recovery"
    HARD_SESSION_RECENTLY = "hard_session_recently"
    ENOUGH_HARD_SESSIONS = "enough_hard_sessions"
    HARD_SESSION_DUE = "hard_session_due"


class CategoryDecision(BaseModel):
    """The coarse half of a recommendation: what kind of day today is.

    Attributes:
        category: The suggested category, always one of
            :data:`SUGGESTABLE_CATEGORIES`.
        reason: Which rule decided it.
        hard_sessions: How many sessions in the window were interval
            sessions.
        sessions_seen: How many past sessions the window actually held,
            which is below the window size early on.
    """

    category: WorkoutCategory
    reason: SuggestionReason
    hard_sessions: NonNegativeInt
    sessions_seen: NonNegativeInt


def _is_hard(session: SessionSummary) -> bool:
    """Whether a past session counts as a hard one.

    Read from the athlete's own tag rather than from the detected interval
    type: a session tagged as intervals was ridden as one, even if no
    blocks could be detected in it afterwards for want of an FTP value.
    """
    return session.category is WorkoutCategory.INTERVALLE


@deal.pre(
    lambda sessions, today, recovery_score=None: (
        recovery_score is None or 0 <= recovery_score <= 100
    )
)
@deal.ensure(lambda _: _.result.category in SUGGESTABLE_CATEGORIES)
@deal.ensure(lambda _: _.result.hard_sessions <= _.result.sessions_seen)
def decide_category(
    sessions: list[SessionSummary],
    today: date,
    recovery_score: int | None = None,
) -> CategoryDecision:
    """Decide whether today calls for intervals, base training, or recovery.

    The rules are checked in order, hardest constraint first: a red
    recovery day overrides everything, because suggesting intervals to
    someone whose body is reporting that it has not recovered is the one
    piece of actively bad advice this feature could give. Base training is
    the fallback throughout and carries no upper limit of its own — it is
    the volume the rest is built on, so there is no such thing as too much
    of it in this model.

    Args:
        sessions: The recent sessions, oldest first, as returned by
            :func:`~suggestion.history.recent_sessions`.
        today: The day being planned.
        recovery_score: Today's Whoop recovery score in percent, or None
            if no recovery data covers today.

    Returns:
        The coarse decision together with the rule that produced it.

    Raises:
        deal.PreContractError: If ``recovery_score`` is outside 0–100.

    >>> from datetime import date
    >>> def session(day: int, category: WorkoutCategory) -> SessionSummary:
    ...     return SessionSummary(
    ...         date=date(2026, 7, day), category=category, interval_type=None
    ...     )
    >>> today = date(2026, 7, 20)
    >>> easy = [session(day, WorkoutCategory.GRUNDLAGE) for day in (10, 12, 14)]
    >>> decide_category(easy, today).category
    <WorkoutCategory.INTERVALLE: 'intervalle'>
    >>> decide_category(easy, today, recovery_score=20).category
    <WorkoutCategory.RECOVERY: 'recovery'>
    >>> decide_category([], today).reason
    <SuggestionReason.NO_HISTORY: 'no_history'>
    """
    hard_sessions = sum(1 for session in sessions if _is_hard(session))

    def decision(
        category: WorkoutCategory, reason: SuggestionReason
    ) -> CategoryDecision:
        return CategoryDecision(
            category=category,
            reason=reason,
            hard_sessions=hard_sessions,
            sessions_seen=len(sessions),
        )

    if recovery_score is not None and recovery_score <= RECOVERY_RED_MAX:
        return decision(WorkoutCategory.RECOVERY, SuggestionReason.LOW_RECOVERY)

    if not sessions:
        return decision(WorkoutCategory.GRUNDLAGE, SuggestionReason.NO_HISTORY)

    rested_since = today - timedelta(days=_HARD_SESSION_REST_DAYS)
    if any(_is_hard(session) and session.date >= rested_since for session in sessions):
        return decision(
            WorkoutCategory.GRUNDLAGE, SuggestionReason.HARD_SESSION_RECENTLY
        )

    if hard_sessions >= MAX_HARD_SESSIONS:
        return decision(
            WorkoutCategory.GRUNDLAGE, SuggestionReason.ENOUGH_HARD_SESSIONS
        )

    return decision(WorkoutCategory.INTERVALLE, SuggestionReason.HARD_SESSION_DUE)
