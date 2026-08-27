"""Tests for suggestion.suggest."""

from datetime import date

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from intervals import IntervalType
from models import WorkoutCategory
from suggestion.history import SessionSummary
from suggestion.interval_choice import SUGGESTABLE_TYPES
from suggestion.rules import RECOVERY_YELLOW_MAX, SUGGESTABLE_CATEGORIES
from suggestion.suggest import GRUNDLAGE_BAND, suggest_training

TODAY = date(2026, 7, 20)
FTP = 200


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


def _easy_history() -> list[SessionSummary]:
    return [_session(days) for days in (12, 10, 8, 6)]


def test_an_interval_day_names_a_type() -> None:
    suggestion = suggest_training(_easy_history(), TODAY, FTP)

    assert suggestion.decision.category is WorkoutCategory.INTERVALLE
    assert suggestion.interval_type in SUGGESTABLE_TYPES


def test_a_base_day_names_no_type() -> None:
    """An interval type on a base day would be a session the athlete was
    explicitly not told to ride."""
    hard = [_session(days, category=WorkoutCategory.INTERVALLE) for days in (12, 9)]

    suggestion = suggest_training(hard, TODAY, FTP)

    assert suggestion.decision.category is WorkoutCategory.GRUNDLAGE
    assert suggestion.interval_type is None


def test_a_recovery_day_names_no_type() -> None:
    suggestion = suggest_training(_easy_history(), TODAY, FTP, recovery_score=20)

    assert suggestion.decision.category is WorkoutCategory.RECOVERY
    assert suggestion.interval_type is None


def test_a_base_day_targets_the_middle_of_the_endurance_band() -> None:
    hard = [_session(days, category=WorkoutCategory.INTERVALLE) for days in (12, 9)]
    expected = round(sum(GRUNDLAGE_BAND) / 2 * FTP)

    assert suggest_training(hard, TODAY, FTP).target_power_w == expected


def test_a_yellow_day_drops_the_target_to_the_bands_lower_edge() -> None:
    """The session must stay what it was prescribed as, just at its
    gentlest end — not become a different session."""
    hard = [_session(days, category=WorkoutCategory.INTERVALLE) for days in (12, 9)]

    yellow = suggest_training(hard, TODAY, FTP, recovery_score=RECOVERY_YELLOW_MAX)

    assert yellow.target_power_w == round(GRUNDLAGE_BAND[0] * FTP)


def test_a_green_day_keeps_the_middle_of_the_band() -> None:
    hard = [_session(days, category=WorkoutCategory.INTERVALLE) for days in (12, 9)]

    green = suggest_training(hard, TODAY, FTP, recovery_score=RECOVERY_YELLOW_MAX + 1)

    assert green.target_power_w == round(sum(GRUNDLAGE_BAND) / 2 * FTP)


def test_a_yellow_day_is_never_harder_than_a_green_one() -> None:
    green = suggest_training(_easy_history(), TODAY, FTP, recovery_score=90)
    yellow = suggest_training(_easy_history(), TODAY, FTP, recovery_score=50)

    assert green.target_power_w is not None
    assert yellow.target_power_w is not None
    assert yellow.target_power_w < green.target_power_w


def test_the_interval_target_lies_inside_the_chosen_types_band() -> None:
    """A sweet-spot session prescribed at threshold wattage would be a
    sweet-spot session in name only."""
    from intervals import classify_relative_power

    suggestion = suggest_training(_easy_history(), TODAY, FTP)

    assert suggestion.target_power_w is not None
    assert classify_relative_power(suggestion.target_power_w / FTP) is (
        suggestion.interval_type
    )


def test_no_ftp_means_no_wattage_but_still_a_session() -> None:
    suggestion = suggest_training(_easy_history(), TODAY)

    assert suggestion.target_power_w is None
    assert suggestion.decision.category in SUGGESTABLE_CATEGORIES


def test_an_empty_history_still_yields_a_suggestion() -> None:
    suggestion = suggest_training([], TODAY, FTP)

    assert suggestion.decision.category is WorkoutCategory.GRUNDLAGE
    assert suggestion.target_power_w is not None


def test_rejects_an_impossible_recovery_score() -> None:
    with pytest.raises(deal.PreContractError):
        suggest_training([], TODAY, FTP, recovery_score=-5)


def test_rejects_a_non_positive_ftp() -> None:
    with pytest.raises(deal.PreContractError):
        suggest_training([], TODAY, ftp_watts=0)


@given(
    hard_days=st.lists(st.integers(min_value=2, max_value=30), max_size=5),
    easy_days=st.lists(st.integers(min_value=0, max_value=30), max_size=5),
    recovery_score=st.one_of(st.none(), st.integers(min_value=0, max_value=100)),
    ftp_watts=st.integers(min_value=80, max_value=500),
)
def test_a_type_is_named_exactly_when_the_day_is_an_interval_day(
    hard_days: list[int],
    easy_days: list[int],
    recovery_score: int | None,
    ftp_watts: int,
) -> None:
    sessions = [
        _session(days, category=WorkoutCategory.INTERVALLE) for days in hard_days
    ] + [_session(days) for days in easy_days]

    suggestion = suggest_training(sessions, TODAY, ftp_watts, recovery_score)

    assert (suggestion.interval_type is not None) == (
        suggestion.decision.category is WorkoutCategory.INTERVALLE
    )


@given(
    recovery_score=st.one_of(st.none(), st.integers(min_value=0, max_value=100)),
    ftp_watts=st.integers(min_value=80, max_value=500),
)
def test_the_target_never_exceeds_the_athletes_own_capability(
    recovery_score: int | None, ftp_watts: int
) -> None:
    """Every band a recommendation draws from tops out below VO2max's
    ceiling, so no suggestion may ever prescribe a sprint."""
    suggestion = suggest_training(_easy_history(), TODAY, ftp_watts, recovery_score)

    assert suggestion.target_power_w is not None
    assert suggestion.target_power_w <= round(1.20 * ftp_watts)
