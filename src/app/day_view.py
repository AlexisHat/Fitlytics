"""Render the selected day's detail: metrics, recovery, and every workout plot."""

from datetime import date
from itertools import pairwise

import polars as pl
import streamlit as st

from analysis.calendar import CalendarDay
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
from models import RecordPoint, RecoveryDay, Workout
from plots import (
    METRICS,
    available_metrics,
    build_gps_map_figure,
    build_time_series,
    build_timeline_figure,
    plot_heart_rate_zones,
    plot_interval_blocks,
    plot_power_zones,
)


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
        f"{workout.start_time.strftime('%H:%M')} — {workout.sport}"
        for workout in workouts
    ]
    choice = st.selectbox(
        "Workout", options=range(len(workouts)), format_func=lambda i: labels[i]
    )
    return workouts[choice if choice is not None else 0]


def _render_metrics(workout: Workout) -> None:
    """Render the workout's key summary metrics as a row of tiles."""
    metrics = compute_workout_metrics(workout)
    columns = st.columns(4)
    columns[0].metric("Dauer (bewegt)", str(metrics.moving_time))
    columns[1].metric(
        "Ø Herzfrequenz",
        f"{metrics.avg_heart_rate:.0f} bpm" if metrics.avg_heart_rate else "–",
    )
    columns[2].metric(
        "Ø Leistung", f"{metrics.avg_power:.0f} W" if metrics.avg_power else "–"
    )
    columns[3].metric(
        "Distanz",
        f"{metrics.distance_m / 1000:.1f} km" if metrics.distance_m else "–",
    )


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
        "Recovery-Score",
        f"{day.recovery_score} %" if day.recovery_score is not None else "–",
    )
    columns[1].metric(
        "Ruhepuls", f"{day.resting_hr} bpm" if day.resting_hr is not None else "–"
    )
    columns[2].metric("HRV", f"{day.hrv_ms:.0f} ms" if day.hrv_ms is not None else "–")


def _render_timeline(series: pl.DataFrame) -> None:
    """Render the interactive multi-panel timeline, skipping if unavailable."""
    try:
        figure = build_timeline_figure(series)
    except AnalysisError:
        st.info("Keine Messreihe für die Zeitachsen-Grafik vorhanden.")
        return
    st.plotly_chart(figure, width="stretch")


def _render_zones(
    records: list[RecordPoint],
    hr_rest: int | None,
    hr_max: int | None,
    ftp_watts: int | None,
) -> None:
    """Render HF- and power-zone bar charts, whichever profile is known."""
    hr_distribution = heart_rate_zone_distribution(records, hr_rest, hr_max)
    power_distribution = power_zone_distribution(records, ftp_watts)
    if hr_distribution is None and power_distribution is None:
        return

    st.subheader("Zonen")
    columns = st.columns(2)
    if hr_distribution is not None:
        columns[0].pyplot(plot_heart_rate_zones(hr_distribution))
    if power_distribution is not None:
        columns[1].pyplot(plot_power_zones(power_distribution))


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
        (
            f"{summary.avg_heart_rate_drift_bpm:+.1f} bpm"
            if summary.avg_heart_rate_drift_bpm is not None
            else "–"
        ),
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
    st.subheader(day.date.isoformat())
    if not day.workouts:
        st.write("Ruhetag.")
        _render_recovery(day.date, recovery_days)
        return

    workout = _select_workout(day.workouts)
    _render_metrics(workout)
    _render_recovery(day.date, recovery_days)

    series = build_time_series(workout.records)
    _render_timeline(series)
    _render_zones(workout.records, hr_rest, hr_max, ftp_watts)
    _render_gps_map(workout, series)
    _render_intervals(workout, ftp_watts)
