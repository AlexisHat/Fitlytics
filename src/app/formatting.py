"""Shared value formatting for the Streamlit views."""

from datetime import timedelta
from typing import Final

from intervals import IntervalType

INTERVAL_TYPE_LABELS: Final[dict[IntervalType, str]] = {
    IntervalType.TEMPO: "Tempo",
    IntervalType.SWEET_SPOT: "Sweet Spot",
    IntervalType.SCHWELLE: "Schwelle",
    IntervalType.VO2MAX: "VO2max",
    IntervalType.ANAEROB: "Anaerob",
    IntervalType.GEMISCHT: "Gemischt",
}
"""German display label per interval type. Kept here rather than on the enum
so the domain layer stays free of display strings, and reachable from both
the day view and the interval close-up without either importing the other."""


def format_optional(value: float | None, template: str) -> str:
    """Format an optional measurement, distinguishing "0" from "not recorded".

    A plain ``value or "–"`` ternary would misrepresent a genuine 0 reading
    (e.g. 0 W while coasting — a real measurement, not a missing one, see
    ``docs/entscheidungen.md``) as unknown. Checking ``is not None``
    explicitly avoids that.

    Args:
        value: The value to format, or None if it wasn't recorded.
        template: A ``str.format`` template with one placeholder for value,
            e.g. ``"{:.0f} W"``.

    Returns:
        The formatted value, or "–" if value is None.

    >>> format_optional(0.0, "{:.0f} W")
    '0 W'
    >>> format_optional(None, "{:.0f} W")
    '–'
    """
    return template.format(value) if value is not None else "–"


def format_interval_type(interval_type: IntervalType | None) -> str:
    """Name an interval type for display, or "–" if it could not be determined.

    Args:
        interval_type: The type, or None if the athlete's FTP is unknown.

    Returns:
        The German label, or "–".

    >>> format_interval_type(IntervalType.SWEET_SPOT)
    'Sweet Spot'
    >>> format_interval_type(None)
    '–'
    """
    return INTERVAL_TYPE_LABELS[interval_type] if interval_type is not None else "–"


def format_minutes(duration: timedelta, signed: bool = False) -> str:
    """Format a duration as minutes with one decimal, optionally signed.

    A signed value is a deviation from the plan, where the sign carries
    the meaning (short vs. long), so it is always shown.

    Args:
        duration: The duration to format.
        signed: Whether to always show the sign.

    Returns:
        The duration in minutes, e.g. ``"4.5 min"`` or ``"+1.0 min"``.

    >>> format_minutes(timedelta(minutes=4, seconds=30))
    '4.5 min'
    >>> format_minutes(timedelta(minutes=-1), signed=True)
    '-1.0 min'
    """
    minutes = duration.total_seconds() / 60
    return f"{minutes:+.1f} min" if signed else f"{minutes:.1f} min"
