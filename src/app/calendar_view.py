"""Render the central calendar view as a clickable, weeks-as-rows grid.

Deliberately plain: a day's intensity is conveyed through the button's
built-in primary/secondary styling and a tooltip, not through a custom
colour ramp — see ``docs/entscheidungen.md`` (Meilenstein 9) for why.
"""

from datetime import date, timedelta

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.calendar import CalendarDay, bucket_training_load

_WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_BUCKET_DESCRIPTIONS = ("Ruhetag", "leicht", "moderat", "hoch", "sehr hoch")


def _week_start(day: date) -> date:
    """Return the Monday of the ISO week ``day`` falls in.

    >>> _week_start(date(2026, 7, 16))
    datetime.date(2026, 7, 13)
    """
    return day - timedelta(days=day.weekday())


def _grid_weeks(days: tuple[CalendarDay, ...]) -> list[list[CalendarDay | None]]:
    """Group calendar days into Monday-start weeks, padding gaps with None.

    Args:
        days: Calendar days covering a contiguous date range, in order; must
            not be empty.

    Returns:
        One list of 7 entries (Monday to Sunday) per week from the first to
        the last day's week, inclusive. A weekday outside ``days``' own
        range (only possible in the first and last week) is None.
    """
    by_date = {day.date: day for day in days}
    week_start = _week_start(days[0].date)
    last_week_start = _week_start(days[-1].date)

    weeks: list[list[CalendarDay | None]] = []
    while week_start <= last_week_start:
        weeks.append(
            [by_date.get(week_start + timedelta(days=offset)) for offset in range(7)]
        )
        week_start += timedelta(days=7)
    return weeks


def _render_day_button(
    column: DeltaGenerator, day: CalendarDay, loads: list[float]
) -> None:
    """Render one clickable day cell and update selected_date on click.

    Args:
        column: The grid column to render the button into.
        day: The day this cell represents.
        loads: Every visible day's training load, for quartile bucketing.
    """
    bucket = bucket_training_load(loads, day.training_load)
    has_workouts = bool(day.workouts)
    label = f"**{day.date.day}**" if has_workouts else str(day.date.day)
    help_text = f"{day.date.isoformat()} — {_BUCKET_DESCRIPTIONS[bucket]}"
    clicked = column.button(
        label,
        key=f"calendar_day_{day.date.isoformat()}",
        type="primary" if has_workouts else "secondary",
        help=help_text,
        width="stretch",
    )
    if clicked:
        st.session_state.selected_date = day.date


def render_calendar(days: tuple[CalendarDay, ...]) -> None:
    """Render the clickable calendar grid, weeks as rows.

    Args:
        days: The calendar days to render, as returned by
            :func:`analysis.calendar.build_calendar`; may be empty.
    """
    if not days:
        st.info("Kalender erscheint, sobald Trainingsdaten hochgeladen sind.")
        return

    loads = [day.training_load for day in days]

    header_columns = st.columns(7)
    for column, label in zip(header_columns, _WEEKDAY_LABELS, strict=True):
        column.markdown(f"**{label}**")

    for week in _grid_weeks(days):
        row_columns = st.columns(7)
        for column, day in zip(row_columns, week, strict=True):
            if day is None:
                column.write("")
            else:
                _render_day_button(column, day, loads)
