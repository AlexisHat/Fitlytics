"""Recommending what to ride today from what was ridden recently."""

from suggestion.history import (
    WINDOW_SIZE,
    SessionSummary,
    recent_sessions,
    session_interval_type,
)
from suggestion.rules import (
    MAX_HARD_SESSIONS,
    SUGGESTABLE_CATEGORIES,
    CategoryDecision,
    SuggestionReason,
    decide_category,
)

__all__ = [
    "MAX_HARD_SESSIONS",
    "SUGGESTABLE_CATEGORIES",
    "WINDOW_SIZE",
    "CategoryDecision",
    "SessionSummary",
    "SuggestionReason",
    "decide_category",
    "recent_sessions",
    "session_interval_type",
]
