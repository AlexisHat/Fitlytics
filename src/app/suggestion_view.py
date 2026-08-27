"""The training recommendation shown at the top of the training page."""

from datetime import date
from typing import Final

import streamlit as st

from app.formatting import INTERVAL_TYPE_LABELS, format_optional
from intervals import IntervalType
from models import RecoveryDay, Workout, WorkoutCategory
from suggestion import (
    CategoryDecision,
    SuggestionReason,
    TrainingSuggestion,
    recent_sessions,
    suggest_training,
)

_RIDE_NAMES: Final[dict[WorkoutCategory, str]] = {
    WorkoutCategory.GRUNDLAGE: "Grundlagenfahrt",
    WorkoutCategory.INTERVALLE: "Intervalle",
    WorkoutCategory.RECOVERY: "Recovery-Fahrt",
}
"""What to call each suggested session in a sentence. Deliberately not the
tag labels from the upload form: "Grundlage" names a category, but a
recommendation names a ride the athlete is about to go and do."""

_INTERVAL_RIDE_NAMES: Final[dict[IntervalType, str]] = {
    IntervalType.SWEET_SPOT: "Sweet-Spot-Intervalle",
    IntervalType.SCHWELLE: "Schwellenintervalle",
    IntervalType.VO2MAX: "VO2max-Intervalle",
}
"""Ride names for the types a recommendation can name, spelled the way a
cyclist would say them rather than assembled from the label plus a suffix,
which would produce "Schwelle-Intervalle"."""

_REASON_TEMPLATES: Final[dict[SuggestionReason, str]] = {
    SuggestionReason.NO_HISTORY: ("Noch keine gespeicherten Fahrten — ruhig anfangen."),
    SuggestionReason.LOW_RECOVERY: (
        "Recovery liegt heute bei {score} % und damit im roten Bereich."
    ),
    SuggestionReason.HARD_SESSION_RECENTLY: (
        "Die letzte harte Einheit liegt noch keinen vollen Tag zurück."
    ),
    SuggestionReason.ENOUGH_HARD_SESSIONS: (
        "{hard} der letzten {seen} Fahrten waren Intervalle — das reicht fürs Erste."
    ),
    SuggestionReason.HARD_SESSION_DUE: (
        "{hard} der letzten {seen} Fahrten waren Intervalle."
    ),
}
"""The German sentence per rule. Kept here rather than in the rule module
so the decision logic stays free of wording, like the interval-type labels."""


def recovery_score_for(days: list[RecoveryDay], today: date) -> int | None:
    """Today's Whoop recovery score, if a day covering today was imported.

    Args:
        days: Every stored recovery day.
        today: The day being planned.

    Returns:
        The score in percent, or None if no imported day covers today or
        the day carries no score.

    >>> from datetime import UTC, date, datetime
    >>> day = RecoveryDay(
    ...     date=date(2026, 7, 20),
    ...     cycle_start=datetime(2026, 7, 20, 1, 0, tzinfo=UTC),
    ...     recovery_score=71,
    ... )
    >>> recovery_score_for([day], date(2026, 7, 20))
    71
    >>> recovery_score_for([day], date(2026, 7, 21))
    """
    match = next((day for day in days if day.date == today), None)
    return match.recovery_score if match is not None else None


def suggestion_headline(suggestion: TrainingSuggestion) -> str:
    """Name the suggested session, with its target wattage where known.

    Args:
        suggestion: The recommendation to phrase.

    Returns:
        A single line such as ``"Schwellenintervalle bei ca. 205 W"``.

    >>> from datetime import date
    >>> from suggestion import CategoryDecision, SuggestionReason
    >>> decision = CategoryDecision(
    ...     category=WorkoutCategory.INTERVALLE,
    ...     reason=SuggestionReason.HARD_SESSION_DUE,
    ...     hard_sessions=0,
    ...     sessions_seen=4,
    ... )
    >>> suggestion_headline(
    ...     TrainingSuggestion(
    ...         decision=decision,
    ...         interval_type=IntervalType.SCHWELLE,
    ...         target_power_w=205,
    ...     )
    ... )
    'Schwellenintervalle bei ca. 205 W'
    >>> suggestion_headline(
    ...     TrainingSuggestion(
    ...         decision=decision.model_copy(
    ...             update={"category": WorkoutCategory.GRUNDLAGE}
    ...         ),
    ...         interval_type=None,
    ...         target_power_w=None,
    ...     )
    ... )
    'Grundlagenfahrt'
    """
    if suggestion.interval_type is not None:
        name = _INTERVAL_RIDE_NAMES.get(
            suggestion.interval_type,
            INTERVAL_TYPE_LABELS[suggestion.interval_type],
        )
    else:
        name = _RIDE_NAMES[suggestion.decision.category]

    if suggestion.target_power_w is None:
        return name
    return f"{name} bei ca. {suggestion.target_power_w} W"


def suggestion_reason_text(
    decision: CategoryDecision, recovery_score: int | None
) -> str:
    """Phrase why the recommendation came out the way it did.

    Args:
        decision: The coarse decision carrying the rule and its counts.
        recovery_score: Today's recovery score, named only by the rule
            that acts on it.

    Returns:
        One sentence.

    >>> from suggestion import CategoryDecision, SuggestionReason
    >>> decision = CategoryDecision(
    ...     category=WorkoutCategory.GRUNDLAGE,
    ...     reason=SuggestionReason.ENOUGH_HARD_SESSIONS,
    ...     hard_sessions=2,
    ...     sessions_seen=5,
    ... )
    >>> suggestion_reason_text(decision, None)
    '2 der letzten 5 Fahrten waren Intervalle — das reicht fürs Erste.'
    """
    return _REASON_TEMPLATES[decision.reason].format(
        hard=decision.hard_sessions,
        seen=decision.sessions_seen,
        score=format_optional(recovery_score, "{:.0f}"),
    )


def render_suggestion(
    workouts: list[Workout],
    recovery_days: list[RecoveryDay],
    profile_ftp: int | None,
    today: date,
) -> None:
    """Render the recommendation panel at the top of the training page.

    Args:
        workouts: Every stored workout.
        recovery_days: Every stored recovery day.
        profile_ftp: The athlete's current FTP, or None if unknown.
        today: The day being planned.
    """
    recovery_score = recovery_score_for(recovery_days, today)
    sessions = recent_sessions(workouts, today, profile_ftp)
    suggestion = suggest_training(sessions, today, profile_ftp, recovery_score)

    with st.container(border=True):
        st.markdown(f"**Vorschlag für heute: {suggestion_headline(suggestion)}**")
        st.caption(suggestion_reason_text(suggestion.decision, recovery_score))
        if recovery_score is None:
            st.caption(
                "Für heute liegen keine Whoop-Daten vor. Mit einem aktuellen "
                "Export wird die Zielleistung an deine Erholung angepasst."
            )
        if profile_ftp is None:
            st.caption(
                "Ohne FTP-Wert in der Seitenleiste lässt sich keine "
                "Zielleistung nennen."
            )
