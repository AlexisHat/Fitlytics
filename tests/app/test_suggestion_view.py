"""Tests for app.suggestion_view's pure helpers."""

from datetime import UTC, date, datetime

from app.suggestion_view import (
    recovery_score_for,
    suggestion_headline,
    suggestion_reason_text,
)
from intervals import IntervalType
from models import RecoveryDay, WorkoutCategory
from suggestion import (
    SUGGESTABLE_TYPES,
    CategoryDecision,
    SuggestionReason,
    TrainingSuggestion,
)

TODAY = date(2026, 7, 20)


def _recovery_day(day: date, score: int | None = 71) -> RecoveryDay:
    return RecoveryDay(
        date=day,
        cycle_start=datetime(day.year, day.month, day.day, 1, 0, tzinfo=UTC),
        recovery_score=score,
    )


def _decision(
    category: WorkoutCategory = WorkoutCategory.INTERVALLE,
    reason: SuggestionReason = SuggestionReason.HARD_SESSION_DUE,
    hard_sessions: int = 0,
    sessions_seen: int = 4,
) -> CategoryDecision:
    return CategoryDecision(
        category=category,
        reason=reason,
        hard_sessions=hard_sessions,
        sessions_seen=sessions_seen,
    )


def _suggestion(
    category: WorkoutCategory = WorkoutCategory.INTERVALLE,
    interval_type: IntervalType | None = IntervalType.SCHWELLE,
    target_power_w: int | None = 205,
) -> TrainingSuggestion:
    return TrainingSuggestion(
        decision=_decision(category=category),
        interval_type=interval_type,
        target_power_w=target_power_w,
    )


def test_recovery_score_for_today() -> None:
    assert recovery_score_for([_recovery_day(TODAY)], TODAY) == 71


def test_recovery_score_is_missing_for_a_day_without_an_export() -> None:
    """A stale export must read as "no data for today" rather than quietly
    reusing the newest score that happens to be stored."""
    stale = [_recovery_day(date(2026, 7, 10))]

    assert recovery_score_for(stale, TODAY) is None


def test_recovery_score_is_missing_when_the_day_carries_none() -> None:
    assert recovery_score_for([_recovery_day(TODAY, score=None)], TODAY) is None


def test_recovery_score_on_an_empty_history() -> None:
    assert recovery_score_for([], TODAY) is None


def test_the_headline_names_the_interval_type_and_the_wattage() -> None:
    assert suggestion_headline(_suggestion()) == "Schwellenintervalle bei ca. 205 W"


def test_the_headline_names_a_base_ride() -> None:
    base = _suggestion(
        category=WorkoutCategory.GRUNDLAGE, interval_type=None, target_power_w=145
    )

    assert suggestion_headline(base) == "Grundlagenfahrt bei ca. 145 W"


def test_the_headline_names_a_recovery_ride() -> None:
    ride = _suggestion(
        category=WorkoutCategory.RECOVERY, interval_type=None, target_power_w=100
    )

    assert suggestion_headline(ride) == "Recovery-Fahrt bei ca. 100 W"


def test_the_headline_drops_the_wattage_when_no_ftp_is_known() -> None:
    """Naming a wattage the app cannot compute would be an invention."""
    assert suggestion_headline(_suggestion(target_power_w=None)) == (
        "Schwellenintervalle"
    )


def test_every_suggestable_type_has_a_ride_name() -> None:
    """A missing entry would surface as a KeyError mid-render."""
    for interval_type in SUGGESTABLE_TYPES:
        headline = suggestion_headline(_suggestion(interval_type=interval_type))
        assert headline
        assert "intervalle" in headline.lower()


def test_the_reason_names_the_counts() -> None:
    decision = _decision(
        category=WorkoutCategory.GRUNDLAGE,
        reason=SuggestionReason.ENOUGH_HARD_SESSIONS,
        hard_sessions=2,
        sessions_seen=5,
    )

    assert suggestion_reason_text(decision, None) == (
        "2 der letzten 5 Fahrten waren Intervalle — das reicht fürs Erste."
    )


def test_the_reason_names_the_recovery_score() -> None:
    decision = _decision(
        category=WorkoutCategory.RECOVERY, reason=SuggestionReason.LOW_RECOVERY
    )

    assert "25" in suggestion_reason_text(decision, 25)


def test_every_reason_has_a_sentence() -> None:
    """Every rule can fire, so every one needs wording — a gap would raise
    a KeyError in the middle of the page."""
    for reason in SuggestionReason:
        assert suggestion_reason_text(_decision(reason=reason), 25)
