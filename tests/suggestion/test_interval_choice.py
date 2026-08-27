"""Tests for suggestion.interval_choice."""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from intervals import IntervalType
from suggestion.history import SessionSummary
from suggestion.interval_choice import SUGGESTABLE_TYPES, choose_interval_type

TODAY = date(2026, 7, 20)


def _ridden(interval_type: IntervalType | None) -> SessionSummary:
    return SessionSummary(
        date=date(2026, 7, 1), category=None, interval_type=interval_type
    )


def test_the_missing_type_is_chosen() -> None:
    sessions = [_ridden(IntervalType.SWEET_SPOT), _ridden(IntervalType.SCHWELLE)]

    assert choose_interval_type(sessions, TODAY) is IntervalType.VO2MAX


def test_the_least_ridden_type_is_chosen_when_all_appear() -> None:
    sessions = [
        _ridden(IntervalType.SWEET_SPOT),
        _ridden(IntervalType.SWEET_SPOT),
        _ridden(IntervalType.VO2MAX),
        _ridden(IntervalType.VO2MAX),
        _ridden(IntervalType.SCHWELLE),
    ]

    assert choose_interval_type(sessions, TODAY) is IntervalType.SCHWELLE


def test_an_empty_history_still_yields_a_type() -> None:
    assert choose_interval_type([], TODAY) in SUGGESTABLE_TYPES


def test_types_that_cannot_be_suggested_are_ignored_in_the_count() -> None:
    """A session that came out as Gemischt or Tempo says nothing about
    which of the three suggestable types is due."""
    sessions = [_ridden(IntervalType.GEMISCHT), _ridden(IntervalType.TEMPO)]
    only_sweet_spot = [*sessions, _ridden(IntervalType.SWEET_SPOT)]

    assert choose_interval_type(only_sweet_spot, TODAY) is not IntervalType.SWEET_SPOT


def test_sessions_without_a_detected_type_are_ignored() -> None:
    sessions = [_ridden(None), _ridden(IntervalType.SWEET_SPOT)]

    assert choose_interval_type(sessions, TODAY) is not IntervalType.SWEET_SPOT


def test_a_tie_is_stable_within_one_day() -> None:
    """A rerun happens on every click; a suggestion that flickered with
    each of them would be unusable."""
    sessions = [_ridden(IntervalType.VO2MAX)]

    repeated = {choose_interval_type(sessions, TODAY) for _ in range(20)}

    assert len(repeated) == 1


def test_a_tie_can_fall_differently_on_another_day() -> None:
    """The tie-break is seeded from the date, so it is not a fixed
    preference for whichever type happens to come first."""
    sessions = [_ridden(IntervalType.VO2MAX)]
    days = [TODAY + timedelta(days=offset) for offset in range(40)]

    chosen = {choose_interval_type(sessions, day) for day in days}

    assert len(chosen) > 1


def test_a_full_tie_between_all_three_stays_within_the_suggestable_types() -> None:
    assert choose_interval_type([], TODAY) in SUGGESTABLE_TYPES


@given(
    types=st.lists(st.sampled_from(list(IntervalType)), max_size=12),
    day_offset=st.integers(min_value=0, max_value=400),
)
def test_only_suggestable_types_are_ever_chosen(
    types: list[IntervalType], day_offset: int
) -> None:
    sessions = [_ridden(interval_type) for interval_type in types]

    chosen = choose_interval_type(sessions, TODAY + timedelta(days=day_offset))

    assert chosen in SUGGESTABLE_TYPES


@given(types=st.lists(st.sampled_from(SUGGESTABLE_TYPES), max_size=12))
def test_the_chosen_type_is_never_ridden_more_often_than_another(
    types: list[IntervalType],
) -> None:
    """Whatever the tie-break does, it may only ever pick from the types
    that are already the least ridden."""
    sessions = [_ridden(interval_type) for interval_type in types]

    chosen = choose_interval_type(sessions, TODAY)

    assert types.count(chosen) == min(
        types.count(candidate) for candidate in SUGGESTABLE_TYPES
    )
