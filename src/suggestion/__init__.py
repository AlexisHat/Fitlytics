"""Recommending what to ride today from what was ridden recently."""

from suggestion.history import (
    WINDOW_SIZE,
    SessionSummary,
    recent_sessions,
    session_interval_type,
)
from suggestion.interval_choice import SUGGESTABLE_TYPES, choose_interval_type
from suggestion.rules import (
    MAX_HARD_SESSIONS,
    SUGGESTABLE_CATEGORIES,
    CategoryDecision,
    SuggestionReason,
    decide_category,
)
from suggestion.suggest import TrainingSuggestion, suggest_training

__all__ = [
    "MAX_HARD_SESSIONS",
    "SUGGESTABLE_CATEGORIES",
    "SUGGESTABLE_TYPES",
    "WINDOW_SIZE",
    "CategoryDecision",
    "SessionSummary",
    "SuggestionReason",
    "TrainingSuggestion",
    "choose_interval_type",
    "decide_category",
    "recent_sessions",
    "session_interval_type",
    "suggest_training",
]
