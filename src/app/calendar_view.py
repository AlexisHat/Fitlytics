"""Render the central calendar view: one month at a time, with navigation.

A trained day's button is tinted green-to-red by how hard it was, on a fixed
0-100% scale — see ``docs/entscheidungen.md`` (Meilenstein 9) for why the
scale is a fixed TSS reference rather than relative to the shown month, and
why it runs through multiple hues instead of staying in one.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Final

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.calendar import CalendarDay, build_calendar, training_load_intensity_pct
from models import Workout
from plots.intensity import intensity_color, intensity_rgb

_WEEKDAY_LABELS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_MONTH_LABELS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)

_BRIGHTNESS_THRESHOLD: Final = 150
"""Below this perceived brightness (YIQ formula, 0-255), white text reads
better against the intensity background than the theme's dark text."""


def _perceived_brightness(rgb: tuple[int, int, int]) -> float:
    """YIQ perceived brightness of an RGB colour, 0 (black) to 255 (white).

    >>> round(_perceived_brightness((255, 255, 255)))
    255
    >>> round(_perceived_brightness((0, 0, 0)))
    0
    """
    r, g, b = rgb
    return (r * 299 + g * 587 + b * 114) / 1000


def _readable_text_color(pct: int) -> str:
    """Pick white or the theme's dark text so the day number stays legible.

    Reads the actual interpolated background's brightness rather than
    assuming it darkens monotonically with ``pct`` — true for the old
    single-hue blue ramp, but not for a multi-hue one where e.g. the yellow
    midpoint is brighter than the green step before it.

    >>> _readable_text_color(0)
    '#31333F'
    >>> _readable_text_color(50)
    '#31333F'
    >>> _readable_text_color(100)
    '#FFFFFF'
    """
    brightness = _perceived_brightness(intensity_rgb(pct))
    return "#31333F" if brightness >= _BRIGHTNESS_THRESHOLD else "#FFFFFF"


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


def _shift_month(month: date, delta: int) -> date:
    """Return the 1st of the month ``delta`` months away from ``month``.

    Args:
        month: Any date within the reference month.
        delta: How many months to shift, negative for earlier months.

    Returns:
        The 1st of the shifted month.

    >>> _shift_month(date(2026, 7, 1), 1)
    datetime.date(2026, 8, 1)
    >>> _shift_month(date(2026, 1, 1), -1)
    datetime.date(2025, 12, 1)
    """
    total_months = month.year * 12 + (month.month - 1) + delta
    year, month_index = divmod(total_months, 12)
    return date(year, month_index + 1, 1)


def _default_month(workouts: Sequence[Workout]) -> date:
    """The month to show before the user has navigated anywhere.

    Args:
        workouts: Every uploaded workout; must not be empty.

    Returns:
        The 1st of the most recent workout's month.
    """
    latest = max(workout.start_time for workout in workouts)
    return date(latest.year, latest.month, 1)


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


def _day_tooltip(day: CalendarDay, pct: int) -> str:
    """Build a trained day's tooltip: its workout names and load percentage.

    Names rather than the date, since the date is already the button's own
    label — the tooltip should add what the label can't show, which is
    which session(s) this was and how hard.

    Args:
        day: The day the tooltip is for; must have at least one workout.
        pct: The day's training-load intensity, from
            :func:`~analysis.calendar.training_load_intensity_pct`.

    Returns:
        The workouts' display names, joined with ", " if there is more
        than one, followed by the load percentage.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint, Workout
    >>> start = datetime(2026, 7, 16, 14, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, power=200)]
    >>> workout = Workout(start_time=start, sport="cycling", records=records)
    >>> day = CalendarDay(date=start.date(), training_load=50.0, workouts=(workout,))
    >>> _day_tooltip(day, 42)
    'Training am 2026-07-16 — 42%'
    """
    names = ", ".join(workout.display_name for workout in day.workouts)
    return f"{names} — {pct}%"


def _render_day_button(column: DeltaGenerator, day: CalendarDay) -> None:
    """Render one clickable day cell and update selected_date on click.

    A trained day's button is tinted green-to-red by its fixed-scale
    intensity (see :func:`_intensity_color`); a rest day keeps Streamlit's
    plain secondary button style.

    Args:
        column: The grid column to render the button into.
        day: The day this cell represents.
    """
    has_workouts = bool(day.workouts)
    label = f"**{day.date.day}**" if has_workouts else str(day.date.day)
    key = f"calendar_day_{day.date.isoformat()}"

    if has_workouts:
        pct = training_load_intensity_pct(day.training_load)
        color = intensity_color(pct)
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
        help_text = _day_tooltip(day, pct)
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


def _render_month_nav(month: date) -> date:
    """Render the prev/next month buttons and the "Month Year" header.

    A click updates ``st.session_state.calendar_month`` mid-run rather than
    starting a fresh one, so the header (and the caller's grid) must read
    the value back afterwards instead of continuing to use ``month`` —
    otherwise this same run would render the old month once more and only
    catch up on the next, unrelated rerun.

    Args:
        month: The month shown before this render (any date within it).

    Returns:
        The month to actually display this run: ``month`` unless the user
        just clicked prev or next.
    """
    prev_column, header_column, next_column = st.columns([1, 5, 1])
    if prev_column.button("◀", key="calendar_prev_month", width="stretch"):
        st.session_state.calendar_month = _shift_month(month, -1)
    if next_column.button("▶", key="calendar_next_month", width="stretch"):
        st.session_state.calendar_month = _shift_month(month, 1)

    month = st.session_state.calendar_month
    header_column.markdown(f"### {_MONTH_LABELS[month.month - 1]} {month.year}")
    return month


def render_calendar(
    workouts: Sequence[Workout],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> tuple[CalendarDay, ...]:
    """Render one month of the calendar at a time, with prev/next navigation.

    Args:
        workouts: Every workout to aggregate into the shown month; may be
            empty, in which case no calendar is rendered yet.
        ftp_watts: The athlete's FTP, or None if unknown — used only to
            decide whether to hint that intensity colouring needs a
            profile, not for any calculation here.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The currently shown month's calendar days, so the caller can look
        up a clicked day without recomputing the month itself. Empty if
        ``workouts`` is empty.
    """
    if not workouts:
        st.info("Kalender erscheint, sobald Trainingsdaten hochgeladen sind.")
        return ()

    if "calendar_month" not in st.session_state:
        st.session_state.calendar_month = _default_month(workouts)

    month = _render_month_nav(st.session_state.calendar_month)

    if _profile_missing(ftp_watts, hr_rest, hr_max):
        st.info(
            "Gib FTP und/oder Ruhepuls/Maximalpuls in der Sidebar ein, damit "
            "die Tage hier nach Trainingsbelastung eingefärbt werden können."
        )

    days = build_calendar(workouts, month.year, month.month, ftp_watts, hr_rest, hr_max)

    header_columns = st.columns(7)
    for column, label in zip(header_columns, _WEEKDAY_LABELS, strict=True):
        column.markdown(f"**{label}**")

    for week in _grid_weeks(days):
        row_columns = st.columns(7)
        for column, day in zip(row_columns, week, strict=True):
            if day is None:
                column.write("")
            else:
                _render_day_button(column, day)

    return days
