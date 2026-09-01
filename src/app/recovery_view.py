"""Render the recovery page: Whoop figures over time rather than per day."""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Final

import streamlit as st

from analysis import average
from analysis.calendar import daily_training_load
from models import RecoveryDay, Workout
from plots.recovery_trend import plot_recovery_trend

PERIOD_DAYS: Final[dict[str, int | None]] = {
    "30 Tage": 30,
    "90 Tage": 90,
    "1 Jahr": 365,
    "Alles": None,
}
"""Selectable time spans, None meaning the full history. A year of daily
values drawn at once is unreadable, so the default is a shorter window the
athlete can widen."""

_DEFAULT_PERIOD: Final = "90 Tage"


def limit_to_period(
    days: list[RecoveryDay], period_days: int | None, today: date
) -> list[RecoveryDay]:
    """Keep only the recovery days within the last ``period_days``.

    Counted back from ``today`` rather than from the newest stored day, so
    a gap since the last Whoop export shows up as a gap instead of being
    silently closed by shifting the window.

    Args:
        days: The stored recovery days in chronological order.
        period_days: How many days back to keep, or None for all of them.
        today: The day the window is counted back from.

    Returns:
        The subset of ``days`` within the window, in the same order.

    >>> from datetime import UTC, date, datetime
    >>> days = [
    ...     RecoveryDay(
    ...         date=date(2026, 7, day),
    ...         cycle_start=datetime(2026, 7, day, 1, 0, tzinfo=UTC),
    ...     )
    ...     for day in (1, 15, 20)
    ... ]
    >>> [day.date.day for day in limit_to_period(days, 10, date(2026, 7, 21))]
    [15, 20]
    >>> [day.date.day for day in limit_to_period(days, None, date(2026, 7, 21))]
    [1, 15, 20]
    """
    if period_days is None:
        return days
    earliest = today - timedelta(days=period_days)
    return [day for day in days if day.date >= earliest]


def _render_summary(days: list[RecoveryDay]) -> None:
    """Show the period's average recovery figures as a row of tiles."""
    scores = [day.recovery_score for day in days if day.recovery_score is not None]
    hrvs = [day.hrv_ms for day in days if day.hrv_ms is not None]
    resting = [day.resting_hr for day in days if day.resting_hr is not None]

    columns = st.columns(4)
    columns[0].metric("Tage", len(days))
    columns[1].metric("Ø Recovery", f"{average(scores):.0f} %" if scores else "–")
    columns[2].metric("Ø HRV", f"{average(hrvs):.0f} ms" if hrvs else "–")
    columns[3].metric("Ø Ruhepuls", f"{average(resting):.0f} bpm" if resting else "–")


def render_recovery(
    days: list[RecoveryDay],
    workouts: Sequence[Workout],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> None:
    """Render the recovery page for every stored Whoop day.

    Args:
        days: Every stored recovery day, in chronological order.
        workouts: Every stored workout, marked onto the chart by how hard
            it was; an empty sequence simply draws no markers.
        ftp_watts: The athlete's Functional Threshold Power, or None if
            unknown — without it a ride's load falls back to TRIMP.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.
    """
    st.subheader("Recovery")

    if not days:
        st.info("Noch keine Whoop-Daten vorhanden — CSV in der Seitenleiste hochladen.")
        return

    period = st.segmented_control(
        "Zeitraum",
        options=list(PERIOD_DAYS),
        default=_DEFAULT_PERIOD,
        label_visibility="collapsed",
    )
    period_days = PERIOD_DAYS[period or _DEFAULT_PERIOD]
    selected = limit_to_period(days, period_days, date.today())

    if not selected:
        st.info("Im gewählten Zeitraum liegen keine Recovery-Daten.")
        return

    _render_summary(selected)
    loads = daily_training_load(workouts, ftp_watts, hr_rest, hr_max)
    st.pyplot(plot_recovery_trend(selected, loads))
    if loads:
        st.caption(
            "Senkrechte Linien markieren Trainingstage, eingefärbt nach der "
            "Belastung des Tages — grün locker bis rot hart, dieselbe Skala "
            "wie im Kalender."
        )
