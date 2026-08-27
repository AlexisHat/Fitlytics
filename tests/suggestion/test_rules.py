"""Tests for suggestion.rules."""

from datetime import date

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals import IntervalType
from models import WorkoutCategory
from suggestion.history import SessionSummary
from suggestion.rules import (
    MAX_HARD_SESSIONS,
    RECOVERY_RED_MAX,
    SUGGESTABLE_CATEGORIES,
    SuggestionReason,
    decide_category,
)

TODAY = date(2026, 7, 20)


def _session(
    days_ago: int,
    category: WorkoutCategory | None = WorkoutCategory.GRUNDLAGE,
    interval_type: IntervalType | None = None,
) -> SessionSummary:
    return SessionSummary(
        date=date.fromordinal(TODAY.toordinal() - days_ago),
        category=category,
        interval_type=interval_type,
    )


def _hard(days_ago: int) -> SessionSummary:
    return _session(days_ago, category=WorkoutCategory.INTERVALLE)


def test_intervals_are_due_after_a_run_of_easy_rides() -> None:
    easy = [_session(days) for days in (10, 8, 6, 4)]

    decision = decide_category(easy, TODAY)

    assert decision.category is WorkoutCategory.INTERVALLE
    assert decision.reason is SuggestionReason.HARD_SESSION_DUE


def test_no_history_starts_with_base_training() -> None:
    decision = decide_category([], TODAY)

    assert decision.category is WorkoutCategory.GRUNDLAGE
    assert decision.reason is SuggestionReason.NO_HISTORY


def test_a_red_recovery_day_overrides_everything() -> None:
    """Suggesting intervals to someone whose body reports it has not
    recovered is the one actively harmful thing this feature could do."""
    easy = [_session(days) for days in (10, 8, 6, 4)]

    decision = decide_category(easy, TODAY, recovery_score=20)

    assert decision.category is WorkoutCategory.RECOVERY
    assert decision.reason is SuggestionReason.LOW_RECOVERY


def test_a_red_recovery_day_overrides_an_empty_history() -> None:
    assert decide_category([], TODAY, recovery_score=10).reason is (
        SuggestionReason.LOW_RECOVERY
    )


def test_the_red_band_includes_its_upper_bound() -> None:
    assert decide_category([], TODAY, recovery_score=RECOVERY_RED_MAX).category is (
        WorkoutCategory.RECOVERY
    )


def test_just_above_the_red_band_no_longer_vetoes() -> None:
    decision = decide_category([], TODAY, recovery_score=RECOVERY_RED_MAX + 1)

    assert decision.category is WorkoutCategory.GRUNDLAGE


def test_a_green_recovery_day_does_not_veto() -> None:
    easy = [_session(days) for days in (10, 8, 6)]

    assert decide_category(easy, TODAY, recovery_score=90).category is (
        WorkoutCategory.INTERVALLE
    )


def test_no_recovery_data_does_not_veto() -> None:
    easy = [_session(days) for days in (10, 8, 6)]

    assert decide_category(easy, TODAY).category is WorkoutCategory.INTERVALLE


def test_a_hard_session_yesterday_blocks_another() -> None:
    decision = decide_category([_hard(1)], TODAY)

    assert decision.category is WorkoutCategory.GRUNDLAGE
    assert decision.reason is SuggestionReason.HARD_SESSION_RECENTLY


def test_a_hard_session_today_blocks_another() -> None:
    assert decide_category([_hard(0)], TODAY).reason is (
        SuggestionReason.HARD_SESSION_RECENTLY
    )


def test_a_hard_session_two_days_ago_no_longer_blocks() -> None:
    assert decide_category([_hard(2)], TODAY).category is WorkoutCategory.INTERVALLE


def test_a_hard_session_yesterday_blocks_even_behind_a_later_easy_ride() -> None:
    """The rest rule asks whether any hard session was recent, not whether
    the most recent session happened to be a hard one."""
    sessions = [_hard(1), _session(0)]

    assert decide_category(sessions, TODAY).reason is (
        SuggestionReason.HARD_SESSION_RECENTLY
    )


def test_enough_hard_sessions_in_the_window_calls_for_base_training() -> None:
    sessions = [_hard(days) for days in (12, 9)] + [_session(6), _session(4)]

    decision = decide_category(sessions, TODAY)

    assert decision.category is WorkoutCategory.GRUNDLAGE
    assert decision.reason is SuggestionReason.ENOUGH_HARD_SESSIONS


def test_one_hard_session_below_the_limit_still_allows_intervals() -> None:
    sessions = [_hard(12), _session(9), _session(6), _session(4)]

    assert decide_category(sessions, TODAY).category is WorkoutCategory.INTERVALLE


def test_base_training_has_no_upper_limit_of_its_own() -> None:
    """Base training is the volume the rest is built on; a window full of
    it must not push the athlete into intervals against the other rules."""
    easy = [_session(days) for days in (12, 10, 8, 6, 4)]

    assert decide_category(easy, TODAY).category is WorkoutCategory.INTERVALLE


def test_hard_sessions_are_counted_from_the_athletes_tag() -> None:
    """A session tagged as intervals was ridden as one, even if no blocks
    could be detected in it for want of an FTP value."""
    sessions = [_hard(12), _hard(9)]

    assert decide_category(sessions, TODAY).hard_sessions == 2


def test_an_untagged_session_does_not_count_as_hard() -> None:
    sessions = [_session(12, category=None), _session(9, category=None)]

    assert decide_category(sessions, TODAY).hard_sessions == 0


def test_a_groupride_does_not_count_as_hard() -> None:
    sessions = [_session(days, category=WorkoutCategory.GROUPRIDE) for days in (12, 9)]

    assert decide_category(sessions, TODAY).hard_sessions == 0


def test_the_window_size_is_reported() -> None:
    sessions = [_session(days) for days in (12, 10, 8)]

    assert decide_category(sessions, TODAY).sessions_seen == 3


def test_rejects_an_impossible_recovery_score() -> None:
    with pytest.raises(deal.PreContractError):
        decide_category([], TODAY, recovery_score=120)


@given(
    hard_days=st.lists(st.integers(min_value=0, max_value=30), max_size=6),
    easy_days=st.lists(st.integers(min_value=0, max_value=30), max_size=6),
    recovery_score=st.one_of(st.none(), st.integers(min_value=0, max_value=100)),
)
def test_only_plannable_categories_are_ever_suggested(
    hard_days: list[int], easy_days: list[int], recovery_score: int | None
) -> None:
    """A group ride cannot be prescribed and "Sonstige" says nothing, so
    neither may reach the athlete as a recommendation."""
    sessions = [_hard(days) for days in hard_days] + [
        _session(days) for days in easy_days
    ]

    decision = decide_category(sessions, TODAY, recovery_score)

    assert decision.category in SUGGESTABLE_CATEGORIES


@given(hard_count=st.integers(min_value=MAX_HARD_SESSIONS, max_value=8))
def test_intervals_are_never_suggested_once_the_window_is_full_of_them(
    hard_count: int,
) -> None:
    sessions = [_hard(days_ago=5 + index) for index in range(hard_count)]

    assert decide_category(sessions, TODAY).category is not WorkoutCategory.INTERVALLE
