"""Render the selected day's detail: metrics, recovery, and every workout plot."""

from datetime import date
from itertools import pairwise
from typing import Final, Literal

import polars as pl
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.calendar import CalendarDay
from analysis.constants import DEFAULT_POWER_ZONE_MODEL, PowerZoneModel
from analysis.heart_rate_zones import heart_rate_zone_distribution
from analysis.power_zones import power_zone_distribution
from analysis.workout import compute_workout_metrics
from errors import AnalysisError
from intervals import (
    DEFAULT_SCALE,
    IntervalBlock,
    IntervalSummary,
    build_interval_blocks,
    compute_baseline,
    find_candidates,
    mark_standstill,
    resample_to_1hz,
    summarize_interval_blocks,
)
from models import RecordPoint, RecoveryDay, Workout, WorkoutCategory
from plots import (
    METRICS,
    POWER_ZONE_MODEL_LABELS,
    available_metrics,
    build_gps_map_figure,
    build_time_series,
    build_timeline_figure,
    plot_heart_rate_zones,
    plot_interval_blocks,
    plot_power_zones,
)

WORKOUT_CATEGORY_LABELS: Final[dict[WorkoutCategory, str]] = {
    WorkoutCategory.GRUNDLAGE: "Grundlage",
    WorkoutCategory.INTERVALLE: "Intervalle",
    WorkoutCategory.GROUPRIDE: "Groupride",
    WorkoutCategory.RECOVERY: "Recovery",
    WorkoutCategory.SONSTIGE: "Sonstige",
}
"""German display label per training category, shared by the upload
selectbox (:mod:`app.main`) and this module's category badge."""

_BadgeColor = Literal[
    "red", "orange", "yellow", "blue", "green", "violet", "gray", "grey", "primary"
]
"""Mirrors ``st.badge``'s own ``color`` parameter type, which streamlit does
not export as a reusable name."""

_WORKOUT_CATEGORY_BADGE_COLORS: Final[dict[WorkoutCategory, _BadgeColor]] = {
    WorkoutCategory.GRUNDLAGE: "blue",
    WorkoutCategory.INTERVALLE: "orange",
    WorkoutCategory.GROUPRIDE: "green",
    WorkoutCategory.RECOVERY: "gray",
    WorkoutCategory.SONSTIGE: "violet",
}
"""Badge colour per category; orange/green match the power/HF panel colours
used elsewhere in the timeline."""


def _format_optional(value: float | None, template: str) -> str:
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

    >>> _format_optional(0.0, "{:.0f} W")
    '0 W'
    >>> _format_optional(None, "{:.0f} W")
    '–'
    """
    return template.format(value) if value is not None else "–"


def _select_workout(workouts: tuple[Workout, ...]) -> Workout:
    """Let the user pick a workout when a day has more than one.

    Args:
        workouts: The day's workouts, in recording order; must not be empty.

    Returns:
        The chosen workout — the only one if there is just one.
    """
    if len(workouts) == 1:
        return workouts[0]

    labels = [
        f"{workout.start_time.strftime('%H:%M')} — {workout.display_name}"
        for workout in workouts
    ]
    choice = st.selectbox(
        "Workout", options=range(len(workouts)), format_func=lambda i: labels[i]
    )
    return workouts[choice if choice is not None else 0]


def _render_title(workout: Workout, day_date: date) -> None:
    """Render the workout's title, with its category badge at the right."""
    title_column, tag_column = st.columns([5, 1])
    title_column.subheader(f"{workout.display_name} — {day_date.isoformat()}")
    if workout.category is not None:
        tag_column.badge(
            WORKOUT_CATEGORY_LABELS[workout.category],
            color=_WORKOUT_CATEGORY_BADGE_COLORS[workout.category],
        )


def _render_planned_intervals(workout: Workout) -> None:
    """Show the plan's interval structure as a caption, if one was entered."""
    plan = workout.planned_intervals
    if plan is None:
        return
    minutes = plan.duration.total_seconds() / 60
    st.caption(
        f"Geplant: {plan.repetitions}× {minutes:.0f} min bei {plan.target_power_w} W"
    )


def _render_metrics(workout: Workout) -> None:
    """Render the workout's key summary metrics as a row of tiles."""
    metrics = compute_workout_metrics(workout)
    distance_km = metrics.distance_m / 1000 if metrics.distance_m is not None else None
    columns = st.columns(4)
    columns[0].metric("Dauer (bewegt)", str(metrics.moving_time))
    columns[1].metric(
        "Ø Herzfrequenz", _format_optional(metrics.avg_heart_rate, "{:.0f} bpm")
    )
    columns[2].metric("Ø Leistung", _format_optional(metrics.avg_power, "{:.0f} W"))
    columns[3].metric("Distanz", _format_optional(distance_km, "{:.1f} km"))


def _render_recovery(
    selected_date: date, recovery_days: tuple[RecoveryDay, ...]
) -> None:
    """Show the day's Whoop recovery metrics, if any were imported for it."""
    day = next((entry for entry in recovery_days if entry.date == selected_date), None)
    if day is None:
        return

    st.subheader("Recovery")
    columns = st.columns(3)
    columns[0].metric(
        "Recovery-Score", _format_optional(day.recovery_score, "{:.0f} %")
    )
    columns[1].metric("Ruhepuls", _format_optional(day.resting_hr, "{:.0f} bpm"))
    columns[2].metric("HRV", _format_optional(day.hrv_ms, "{:.0f} ms"))


def _render_timeline(series: pl.DataFrame) -> None:
    """Render the interactive multi-panel timeline, skipping if unavailable."""
    try:
        figure = build_timeline_figure(series)
    except AnalysisError:
        st.info("Keine Messreihe für die Zeitachsen-Grafik vorhanden.")
        return
    st.plotly_chart(figure, width="stretch")


def _has_power_zone_data(records: list[RecordPoint], ftp_watts: int | None) -> bool:
    """Whether a power-zone chart can be drawn, independent of the chosen model.

    Mirrors the guard inside
    :func:`analysis.power_zones.power_zone_distribution` (FTP known, at
    least two power samples) — the model only changes how those samples are
    bucketed, never whether there is anything to bucket.

    Args:
        records: The workout's record points.
        ftp_watts: The athlete's FTP, or None if unknown.

    Returns:
        True if a power-zone chart can be drawn for this workout.
    """
    if ftp_watts is None:
        return False
    return sum(1 for record in records if record.power is not None) >= 2


def _render_power_zone_plot(
    container: DeltaGenerator, records: list[RecordPoint], ftp_watts: int | None
) -> None:
    """Render the power-zone model picker and the resulting bar chart.

    Assumes :func:`_has_power_zone_data` already confirmed a chart can be
    drawn; still guards the widget's return itself, since Streamlit's
    ``selectbox`` is typed as possibly returning None.
    """
    models = list(PowerZoneModel)
    zone_model = container.selectbox(
        "Leistungszonen-Modell",
        options=models,
        format_func=lambda model: POWER_ZONE_MODEL_LABELS[model],
        index=models.index(DEFAULT_POWER_ZONE_MODEL),
    )
    if zone_model is None:
        return
    distribution = power_zone_distribution(records, ftp_watts, zone_model)
    if distribution is not None:
        container.pyplot(plot_power_zones(distribution))


def _render_zones(
    records: list[RecordPoint],
    hr_rest: int | None,
    hr_max: int | None,
    ftp_watts: int | None,
) -> None:
    """Render HF- and power-zone bar charts, side by side if both are known.

    Falls back to a single full-width chart instead of leaving an empty
    column when only one of the two is available.
    """
    hr_distribution = heart_rate_zone_distribution(records, hr_rest, hr_max)
    has_power_zones = _has_power_zone_data(records, ftp_watts)
    if hr_distribution is None and not has_power_zones:
        return

    st.subheader("Zonen")
    if hr_distribution is not None and has_power_zones:
        hr_column, power_column = st.columns(2)
        hr_column.pyplot(plot_heart_rate_zones(hr_distribution))
        _render_power_zone_plot(power_column, records, ftp_watts)
    elif hr_distribution is not None:
        st.pyplot(plot_heart_rate_zones(hr_distribution))
    else:
        _render_power_zone_plot(st.container(), records, ftp_watts)


def _render_gps_map(workout: Workout, series: pl.DataFrame) -> None:
    """Render the GPS track map with a colour-metric picker, if there is a track."""
    if not workout.has_gps_track:
        return

    metrics = available_metrics(series)
    if not metrics:
        return

    st.subheader("GPS-Karte")
    metric = st.selectbox(
        "Einfärbung", options=metrics, format_func=lambda key: METRICS[key].label
    )
    if metric is None:
        return
    try:
        figure = build_gps_map_figure(series, metric)
    except AnalysisError:
        st.info("Keine Daten für diese Einfärbung.")
        return
    st.plotly_chart(figure, width="stretch")


def _has_strictly_increasing_timestamps(records: list[RecordPoint]) -> bool:
    """Whether ``records`` satisfies the interval pipeline's timing invariant.

    :func:`intervals.resample_to_1hz` requires strictly increasing
    timestamps as a contract precondition — a legitimate invariant for
    internal callers, but ``records`` here comes from a validated,
    real-world FIT file, which only guarantees non-decreasing order. Two
    samples sharing a timestamp is thus a possible real state, not a bug,
    and must not reach that contract as a crash.
    """
    return all(
        earlier.timestamp < later.timestamp for earlier, later in pairwise(records)
    )


def _render_interval_summary(summary: IntervalSummary) -> None:
    """Render the aggregate quality tiles for a workout's interval blocks."""
    columns = st.columns(4)
    columns[0].metric("Anzahl", summary.count)
    columns[1].metric("Ø Gleichmäßigkeit", f"{summary.avg_evenness:.2f}")
    columns[2].metric(
        "Ø Pulsentwicklung",
        _format_optional(summary.avg_heart_rate_drift_bpm, "{:+.1f} bpm"),
    )
    columns[3].metric("Watt-Spanne", f"{summary.power_spread_w:.0f} W")


def _render_interval_table(blocks: list[IntervalBlock]) -> None:
    """Render one row per detected interval block, with the exact numbers."""
    st.dataframe(
        [
            {
                "Start": block.start.strftime("%H:%M:%S"),
                "Dauer": str(block.duration),
                "Ø Watt": round(block.avg_power_w, 1),
                "Ø Puls": (
                    round(block.avg_heart_rate, 1)
                    if block.avg_heart_rate is not None
                    else None
                ),
                "Pulsentwicklung": (
                    round(block.heart_rate_drift_bpm, 1)
                    if block.heart_rate_drift_bpm is not None
                    else None
                ),
                "Gleichmäßigkeit": round(block.evenness, 2),
            }
            for block in blocks
        ]
    )


def _run_interval_analysis(workout: Workout, ftp_watts: int | None) -> None:
    """Compute interval-block detection for one workout and render the result."""
    if not _has_strictly_increasing_timestamps(workout.records):
        st.info("Intervallanalyse nicht möglich: doppelte Zeitstempel in den Rohdaten.")
        return

    series = resample_to_1hz(workout.records)
    series = compute_baseline(series)
    series = mark_standstill(series)
    candidates = find_candidates(series, DEFAULT_SCALE)
    if not candidates:
        st.info("Keine Intervalle erkannt.")
        return

    blocks = build_interval_blocks(series, candidates, ftp_watts)
    st.pyplot(plot_interval_blocks(blocks))
    _render_interval_summary(summarize_interval_blocks(blocks))
    _render_interval_table(blocks)


def _render_intervals(workout: Workout, ftp_watts: int | None) -> None:
    """Run interval-block detection on demand, behind a per-workout button.

    Detection isn't run automatically on every visit: it's a distinct
    computation the user explicitly triggers, not part of the day's
    baseline view.
    """
    state_key = f"interval_analysis_active_{workout.start_time.isoformat()}"
    button_key = f"interval_button_{workout.start_time.isoformat()}"
    if st.button("Intervallanalyse starten", key=button_key):
        st.session_state[state_key] = True

    if not st.session_state.get(state_key, False):
        return

    st.subheader("Intervalle")
    _run_interval_analysis(workout, ftp_watts)


def render_day(
    day: CalendarDay,
    recovery_days: tuple[RecoveryDay, ...],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> None:
    """Render the full detail view for one calendar day: every workout plot.

    Args:
        day: The selected calendar day.
        recovery_days: All imported recovery days, to look the day's own up in.
        ftp_watts: The athlete's FTP, or None if unknown.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.
    """
    if not day.workouts:
        st.subheader(day.date.isoformat())
        st.write("Ruhetag.")
        _render_recovery(day.date, recovery_days)
        return

    workout = _select_workout(day.workouts)
    _render_title(workout, day.date)
    _render_planned_intervals(workout)
    _render_metrics(workout)
    _render_recovery(day.date, recovery_days)

    series = build_time_series(workout.records)
    _render_timeline(series)
    _render_zones(workout.records, hr_rest, hr_max, ftp_watts)
    _render_gps_map(workout, series)
    _render_intervals(workout, ftp_watts)
