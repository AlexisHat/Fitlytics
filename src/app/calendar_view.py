"""Render the central calendar view as a clickable, weeks-as-rows grid.

A trained day's button is tinted blue by how hard it was, relative to the
hardest day in the visible calendar — see ``docs/entscheidungen.md``
(Meilenstein 9) for why the scale is relative rather than a fixed
threshold.
"""

from datetime import date, timedelta
from typing import Final

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.calendar import CalendarDay, training_load_intensity_pct

_WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_INTENSITY_LIGHT: Final = (219, 234, 254)
"""RGB for 0% intensity (Tailwind blue-100)."""

_INTENSITY_DARK: Final = (23, 37, 84)
"""RGB for 100% intensity (Tailwind blue-950)."""

_DARK_TEXT_THRESHOLD_PCT: Final = 50
"""From this intensity on, the background is dark enough that white text
reads better than the theme's default dark text."""


def _intensity_label(pct: int) -> str:
    """Map an intensity percentage to a short German tooltip label.

    >>> _intensity_label(0)
    'Ruhetag'
    >>> _intensity_label(50)
    'moderat'
    >>> _intensity_label(100)
    'extrem hart'
    """
    if pct == 0:
        return "Ruhetag"
    if pct <= 25:
        return "leicht"
    if pct <= 50:
        return "moderat"
    if pct <= 75:
        return "hart"
    return "extrem hart"


def _intensity_color(pct: int) -> str:
    """Interpolate a light-to-dark blue background for a 0-100 intensity.

    >>> _intensity_color(0)
    '#dbeafe'
    >>> _intensity_color(100)
    '#172554'
    """
    fraction = pct / 100
    channels = (
        round(light + (dark - light) * fraction)
        for light, dark in zip(_INTENSITY_LIGHT, _INTENSITY_DARK, strict=True)
    )
    return "#{:02x}{:02x}{:02x}".format(*channels)


def _readable_text_color(pct: int) -> str:
    """Pick white or the theme's dark text so the day number stays legible.

    >>> _readable_text_color(0)
    '#31333F'
    >>> _readable_text_color(100)
    '#FFFFFF'
    """
    return "#FFFFFF" if pct >= _DARK_TEXT_THRESHOLD_PCT else "#31333F"


def _profile_missing(
    ftp_watts: int | None, hr_rest: int | None, hr_max: int | None
) -> bool:
    """Whether no day's colour can be computed for lack of an athlete profile.

    :func:`analysis.load.training_load` needs FTP for TSS or a full
    resting/maximum heart-rate pair for TRIMP; if neither is set, every
    day's training load is 0.0 regardless of the workout data itself, which
    would otherwise silently read as "no training happened" rather than
    "profile missing".

    >>> _profile_missing(None, None, None)
    True
    >>> _profile_missing(210, None, None)
    False
    >>> _profile_missing(None, 50, 190)
    False
    >>> _profile_missing(None, 50, None)
    True
    """
    return ftp_watts is None and (hr_rest is None or hr_max is None)


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

    A trained day's button is tinted blue by its intensity relative to the
    hardest day in ``loads`` (see :func:`_intensity_color`); a rest day
    keeps Streamlit's plain secondary button style.

    Args:
        column: The grid column to render the button into.
        day: The day this cell represents.
        loads: Every visible day's training load, for intensity scaling.
    """
    has_workouts = bool(day.workouts)
    label = f"**{day.date.day}**" if has_workouts else str(day.date.day)
    key = f"calendar_day_{day.date.isoformat()}"

    if has_workouts:
        pct = training_load_intensity_pct(loads, day.training_load)
        color = _intensity_color(pct)
        text_color = _readable_text_color(pct)
        column.html(
            f"<style>.st-key-{key} button, "
            f".st-key-{key} button:hover, "
            f".st-key-{key} button:focus:not(:active) {{"
            f"background-color: {color} !important;"
            f"color: {text_color} !important;"
            f"border-color: {color} !important;"
            "}</style>"
        )
        help_text = f"{day.date.isoformat()} — {pct}% ({_intensity_label(pct)})"
    else:
        help_text = f"{day.date.isoformat()} — Ruhetag"

    clicked = column.button(
        label,
        key=key,
        type="primary" if has_workouts else "secondary",
        help=help_text,
        width="stretch",
    )
    if clicked:
        st.session_state.selected_date = day.date


def render_calendar(
    days: tuple[CalendarDay, ...],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> None:
    """Render the clickable calendar grid, weeks as rows.

    Args:
        days: The calendar days to render, as returned by
            :func:`analysis.calendar.build_calendar`; may be empty.
        ftp_watts: The athlete's FTP, or None if unknown — used only to
            decide whether to hint that intensity colouring needs a
            profile, not for any calculation here.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.
    """
    if not days:
        st.info("Kalender erscheint, sobald Trainingsdaten hochgeladen sind.")
        return

    if _profile_missing(ftp_watts, hr_rest, hr_max):
        st.info(
            "Gib FTP und/oder Ruhepuls/Maximalpuls in der Sidebar ein, damit "
            "die Tage hier nach Trainingsbelastung eingefärbt werden können."
        )

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
